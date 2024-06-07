#!/usr/bin/env python3
import argparse
import copy
import json
import os
import pprint
import sys
import yaml

from typing import Any, Dict, List

from worlds import AutoWorld
import Options

COMMON: Dict[str, Any] = Options.PerGameCommonOptions.type_hints
COMMON["death_link"] = 0
UNSET: str = '__unset'

def parse_opts():
    parser = argparse.ArgumentParser(description="Hyper Enumerator")
    parser.add_argument('-c', '--config_file', default=UNSET, help="Config File for enumerator. \
                        Options can be specified on CLI or via config")
    parser.add_argument('-d', '--dir', default=UNSET, help="Output directory for resultant yaml files.")
    parser.add_argument('-g', '--game', nargs="*", help="Comma-separated list of games to enumerate configs for",
                        default=UNSET, action='append')
    parser.add_argument('-i', '--ignore', help="Comma-seperated list of Options to ignore when exploding enumeration",
                        default=UNSET)
    parser.add_argument('-o', '--options', help="List of options to enumerate", default=UNSET, nargs='+',
                        action='append')
    parser.add_argument('--others', help="whether to set non-specified options as either default or random",
                        default=UNSET, nargs='+', action='append')
    parser.add_argument('-s', '--splits', help="For ranges, number of sections to split range into; minimum 1",
                        default=UNSET)
    parser.add_argument('-v', '--verbose', help="Verbosity; higher prints more.", default=UNSET)
    parser.add_argument('-z', '--zzz', help=argparse.SUPPRESS, default=False, action="store_true")
    args = parser.parse_args()

    # The order of arg preference: CLI > config file > defaults
    # These are the defaults
    cfg: Dict[str, Any] = {
        "dir": '.',
        "game": [],
        "ignore": [],
        "options": [],
        "others": [],
        "splits": 2,
        "verbose": 1
    }

    if args.config_file and args.config_file != UNSET and os.path.isfile(args.config_file):
        tmp_cnf: Dict[str, Any] = {}
        with open(args.config_file, encoding="utf-8") as infile:
            tmp_cnf = yaml.safe_load_all(infile.read())

        for doc in tmp_cnf:
            cfg['game'] = cfg['game'] + [doc['game']]
            if 'options' in doc:
                cfg['options'].append(doc['options'])
            else:
                cfg['options'].append([])
            if 'others' in doc:
                cfg['others'].append(doc['others'])
            else:
                cfg['others'].append('default')

    for key in cfg:
        argval = getattr(args, key, UNSET)
        if argval != UNSET:
            if key == "game" or key == "options":
                cfg[key] = [val.split(',') for val in argval]
            if key == "ignore":
                cfg[key] = argval.split(',')
            else:
                cfg[key] = argval

    if args.zzz:
        print("Options as parsed:")
        pprint.pprint(cfg)
        sys.exit(0)

    return cfg

def get_core_opts(game) -> Dict[str, Any]:
    return {
        f"{game.game}": {
            "progression_balancing": 0,
            "accessibility": "items",
        }
    }

def get_loop_items(game) -> None:
    if 'option_definitions' in dir(game):
        yield from game.option_definitions.items()
    elif 'options_dataclass' in dir(game):
        yield from AutoWorld.AutoWorldRegister.world_types[game.game].options_dataclass.type_hints.items()

def get_base_opts(opts, game, options, behavior='default') -> Dict[str, Any]:
    gm:str = game.game
    base_opts:Dict[str, Any] = get_core_opts(game)

    for opt, cls in get_loop_items(game):
        if opt in COMMON:
            continue
        if opt in opts["ignore"]:
            continue

        # This is what we'll enumerate later
        if opt in options:
            continue

        if issubclass(cls, Options.FreeText):
#           print(f"Game {gm}: Skipping option {opt}, Free Text is not supported")
#           base_opts[gm][opt] = ""
            continue
        if issubclass(cls, Options.TextChoice):
#           print(f"Game {gm}: Skipping option {opt}, Text Choice is not supported")
            continue

        # We don't care what class they are from here, all opts seem to have a default
        if behavior == 'default':
            if isinstance(cls.default, tuple):
                base_opts[gm][opt] = list(cls.default)
            else:
                base_opts[gm][opt] = cls.default
        elif behavior == 'random':
            # just use built-in behavior; easier
            base_opts[gm][opt] = 'random'
        elif behavior == 'minimum':
            if issubclass(cls, Options.Range) or issubclass(cls, Options.NamedRange):
                base_opts[gm][opt] = cls.range_start
            else:
                base_opts[gm][opt] = 0
        elif behavior == 'maximum':
            if issubclass(cls, Options.Range) or issubclass(cls, Options.NamedRange):
                base_opts[gm][opt] = cls.range_end
            else:
                base_opts[gm][opt] = len(cls.options)

    return base_opts

def calculate_radius(opts, game, options) -> int:
    """
        Calculate the blast radius for enumerating the yamls for a given game.
    """
    gm: str = game.game
    radius: int = 1

    for opt, cls in get_loop_items(game):
        if opt in COMMON:
            continue
        if opt in opts["ignore"]:
            continue
        if opt not in options:
            continue

        if issubclass(cls, Options.Toggle) or issubclass(cls, Options.DefaultOnToggle):
            radius *= 2

        elif issubclass(cls, Options.Choice):
            if options[opt] == "all":
                radius *= len(cls.options)
            else:
                radius *= len(options[opt])

        elif issubclass(cls, Options.Range) or issubclass(cls, Options.NamedRange):
            tmp_splits = opts['splits']
            if options[opt] != 'all':
                tmp_splits = options[opt]
            if tmp_splits > cls.range_end - cls.range_start:
                tmp_splits = cls.range_end - cls.range_start

            radius *= tmp_splits + 1

            if issubclass(cls, Options.NamedRange):
                radius *= len(cls.special_range)

    return radius

def enumerate_yaml(opts, game, base, inst, options) -> None:
    """
        Enumerate the YAMLs by doing "yield from" recursively, then yielding at the last step.
    """
    gm: str = game.game
    inst2 = copy.deepcopy(inst)

    # Whether we need to yield a single item (which gets sent back) or recurse again
    last_call: bool = len(base[gm])+len(options)-1 == len(inst[gm])

    for opt, cls in get_loop_items(game):
        if opt in COMMON:
            continue
        if opt in opts["ignore"]:
            continue
        if opt in inst[gm]:
            continue
        if opt not in options:
            continue

        if issubclass(cls, Options.Toggle) or issubclass(cls, Options.DefaultOnToggle):
            print(f"option {opt} is a toggle")
            for val in range(2):
                inst2[gm][opt] = val
                if last_call:
                    yield inst2
                else:
                    yield from enumerate_yaml(opts, game, base, inst2, options)

        elif issubclass(cls, Options.Choice):
            for choice, val in cls.options.items():
                if options[opt] != 'all' and choice not in options[opt]:
                    continue
                inst2[gm][opt] = val
                if last_call:
                    yield inst2
                else:
                    yield from enumerate_yaml(opts, game, base, inst2, options)

        elif issubclass(cls, Options.Range) or issubclass(cls, Options.NamedRange):
            tmp_splits = opts['splits']
            if options[opt] != 'all':
                tmp_splits = options[opt]
            if tmp_splits > cls.range_end - cls.range_start:
                tmp_splits = cls.range_end - cls.range_start
            val = cls.range_start
            while val <= cls.range_end:
                inst2[gm][opt] = round(val)
                if last_call:
                    yield inst2
                else:
                    yield from enumerate_yaml(opts, game, base, inst2, options)
                val += (cls.range_end - cls.range_start) / tmp_splits

            if issubclass(cls, Options.NamedRange):
                for val in cls.special_range:
                    inst2[gm][opt] = val
                    if last_call:
                        yield inst2
                    else:
                        yield from enumerate_yaml(opts, game, base, inst2, options)

def hyper_enumerator() -> None:
    opts = parse_opts()

    if len(opts["game"]) < 1:
        print("Must supply a list of games for which to enumerate configs.")
        sys.exit(1)

    processed = []
    processing: int = 0
    for cls in AutoWorld.AutoWorldRegister.world_types.values():
        if cls.game not in opts['game']:
            continue
        for gameno in range(len(opts['game'])):
            if opts['game'][gameno] == cls.game:
                processing = gameno
                break
        base = get_base_opts(opts, cls, opts['options'][processing], opts['others'][processing])
        inst = get_base_opts(opts, cls, opts['options'][processing], opts['others'][processing])

        blast_radius: int = calculate_radius(opts, cls, opts['options'][processing])
        if blast_radius > 1000:
            print(f"Enumerating the YAMLs for {cls.game} would be large: {blast_radius}")
            answer: str = input("Are you sure you want to proceed? [y/N] ")
            if answer.lower() not in ["y","yes"]:
                continue

        counter = 0
        game_name = '_'.join(cls.game.split())
        # TODO: figure out why we're getting dupes (and remove them)
        cache = {}
        with open(f"{opts['dir']}/{game_name}.yaml", 'w', encoding="utf-8") as out_yaml:
            for yml in enumerate_yaml(opts, cls, base, inst, opts['options'][processing]):
                if json.dumps(yml, sort_keys=True) in cache:
                    continue
                cache[json.dumps(yml, sort_keys=True)] = 1
                if counter > 0:
                    out_yaml.write("---\n")
                counter += 1
                out_yaml.write("\n")
                out_yaml.write(f"name: {game_name[0:12]}{counter}\n")
                out_yaml.write(f"description: {cls.game} - {counter}\n")
                out_yaml.write(f"game: {cls.game}\n")
                out_yaml.write(yaml.dump(yml))
                out_yaml.write("\n")

        processed = processed + [cls.game]

    print(f"\nFinished! Wrote {len(processed)} game files:")
    for game in processed:
        print(f"- {game}")

    if len(processed) < len(opts["game"]):
        print("\nDidn't process some games:")
        for game in opts["game"]:
            if game not in processed:
                print(f"- {game}")

if __name__ == '__main__':
    hyper_enumerator()
    sys.exit(0)

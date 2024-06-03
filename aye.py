#!/usr/bin/env python3
import argparse
import copy
import itertools
import os
import pprint
import sys
import types
import yaml
import json

from worlds import AutoWorld
import Options

COMMON = Options.PerGameCommonOptions.type_hints
COMMON["death_link"] = 0
UNSET = '__unset'

def parse_opts():
    parser = argparse.ArgumentParser(description="Hyper Enumerator")
    parser.add_argument('-c', '--config_file', default=UNSET, help="Config File for enumerator. \
                        Options can be specified on CLI or via config")
    parser.add_argument('-d', '--dir', default=UNSET, help="Output directory for resultant yaml files.")
    parser.add_argument('-g', '--game', nargs="*", help="Comma-separated list of games to enumerate configs for",
                        default=UNSET, action='append')
    parser.add_argument('-i', '--ignore', help="Comma-seperated list of Options to ignore when exploding enumeration", default=UNSET)
    parser.add_argument('-o', '--options', help="List of options to enumerate", default=UNSET, nargs='+', action='append')
    parser.add_argument('--others', help="whether to set non-specified options as either default or random", default=UNSET, nargs='+', action='append')
    parser.add_argument('-s', '--splits', help="For ranges, number of sections to split range into; minimum 1", default=UNSET)
    parser.add_argument('-v', '--verbose', help="Verbosity; higher prints more.", default=UNSET)
    parser.add_argument('-z', '--zzz', help=argparse.SUPPRESS, default=False, action="store_true")
    args = parser.parse_args()

    # The order of arg preference: CLI > config file > defaults
    # These are the defaults
    cfg = {
        "dir": '.',
        "game": [],
        "ignore": [],
        "options": [],
        "others": [],
        "splits": 2,
        "verbose": 1
    }

    if args.config_file and args.config_file != UNSET and os.path.isfile(args.config_file):
        tmp_cnf = {}
        with open(args.config_file) as infile:
            tmp_cnf = yaml.safe_load_all(infile.read())

        for g in tmp_cnf:
            cfg['game'] = cfg['game'] + [g['game']]
            if 'options' in g:
                cfg['options'].append(g['options'])
            else:
                cfg['options'].append([])
            if 'others' in g:
                cfg['others'].append(g['others'])
            else:
                cfg['others'].append('default')

    for k in cfg.keys():
        av = getattr(args, k, UNSET)
        if av != UNSET:
            if k == "game" or k == "options":
                cfg[k] = [v.split(',') for v in av]
            if k == "ignore":
                cfg[k] = av.split(',')
            else:
                cfg[k] = av

    if args.zzz:
        print("Options as parsed:")
        pprint.pprint(cfg)
        sys.exit(0)

    return cfg

def get_core_opts(game):
    return {
        f"{game.game}": {
            "progression_balancing": 0,
            "accessibility": "items",
        }
    }

def get_loop_items(game):
    if 'option_definitions' in dir(game):
        return game.option_definitions.items()
    elif 'options_dataclass' in dir(game):
        return AutoWorld.AutoWorldRegister.world_types[game.game].options_dataclass.type_hints.items()

def get_base_opts(opts, game, options, behavior='default'):
    gm = game.game
    base_opts = get_core_opts(game)

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

        # We don't care what class they are from here, all opts have a default?
        if behavior == 'default':
            if type(cls.default) is tuple:
                base_opts[gm][opt] = list(cls.default)
            else:
                base_opts[gm][opt] = cls.default
        elif behavior == 'random':
            base_opts[gm][opt] = 'random'

    return base_opts

# TODO: instead of this, warn if number of yamls > 1000
rip_cord = 1
def enumerate_yaml(opts, game, base, inst, options):
    global rip_cord
    gm = game.game
    inst2 = copy.deepcopy(inst)

    last_call = len(base[gm])+len(options)-1 == len(inst[gm])
    if rip_cord > 5000:
        print("RIP")
        sys.exit(0)
    rip_cord += 1

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
            for i in range(2):
                inst2[gm][opt] = i
                if last_call:
                    yield inst2
                else:
                    yield from enumerate_yaml(opts, game, base, inst2, options)

        elif issubclass(cls, Options.Choice):
            for j, i in cls.options.items():
                if options[opt] != 'all' and j not in options[opt]:
                    continue
                inst2[gm][opt] = i
                if last_call:
                    yield inst2
                else:
                    yield from enumerate_yaml(opts, game, base, inst2, options)

        elif issubclass(cls, Options.Range):
            tmp_splits = opts['splits']
            if options[opt] != 'all':
                tmp_splits = options[opt]
            i = cls.range_start
            while i <= cls.range_end:
                inst2[gm][opt] = round(i)
                if last_call:
                    yield inst2
                else:
                    yield from enumerate_yaml(opts, game, base, inst2, options)
                i += (cls.range_end - cls.range_start) / tmp_splits

        elif issubclass(cls, Options.NamedRange):
            tmp_splits = opts['splits']
            if options[opt] != 'all':
                tmp_splits = options[opt]
            i = cls.range_start
            while i <= cls.range_end:
                inst2[gm][opt] = i
                if last_call:
                    yield inst2
                else:
                    yield from enumerate_yaml(opts, game, base, inst2, options)
                i += round((cls.range_end - cls.range_start) / tmp_splits)

            for i in cls.special_range:
                inst2[gm][opt] = i
                if last_call:
                    yield inst2
                else:
                    yield from enumerate_yaml(opts, game, base, inst2, options)

def hyper_enumerator():
    opts = parse_opts()

    if (len(opts["game"]) < 1):
        print("Must supply a list of games for which to enumerate configs.")
        sys.exit(1)

    processed = []
    processing = 0
    for cls in AutoWorld.AutoWorldRegister.world_types.values():
        if cls.game not in opts['game']:
            continue
        for i in range(len(opts['game'])):
            if opts['game'][i] == cls.game:
                processing = i
                break
        base = get_base_opts(opts, cls, opts['options'][processing], opts['others'][processing])
        inst = get_base_opts(opts, cls, opts['options'][processing], opts['others'][processing])

        counter = 0
        game_name = '_'.join(cls.game.split())
        # TODO: figure out why we're getting dupes (and remove them)
        cache = {}
        with open(f"{opts['dir']}/{game_name}.yaml", 'w') as out_yaml:
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

    print(f"processed {len(processed)} games:")
    for g in processed:
        print(f"- {g}")

    if len(processed) < len(opts["game"]):
        print("Didn't process some games:")
        for g in opts["game"]:
            if g not in processed:
                print(f"  - {g}")

if __name__ == '__main__':
    hyper_enumerator()
    sys.exit(0)

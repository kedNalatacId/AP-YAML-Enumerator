#!/usr/bin/env python3
import argparse
import copy
import json
import os
import pprint
import sys
import yaml

from typing import Any, Dict, List, Tuple, Iterator, Union

from worlds import AutoWorld     # type: ignore
import Options                   # type: ignore

COMMON: Dict[str, Any] = Options.PerGameCommonOptions.type_hints
COMMON["death_link"] = 0
UNSET: str = '__unset'

def parse_opts() -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="Hyper Enumerator")

    parser.add_argument('-b', '--behavior',
                        help="whether to set non-specified options as either default or random",
                        default=UNSET,
                        nargs='+',
                        action='append')
    parser.add_argument('-c', '--config_file',
                        help="Config File for enumerator. Options can be specified on CLI or via config",
                        default=UNSET)
    parser.add_argument('-d', '--dir',
                        help="Output directory for resultant yaml files.",
                        default=UNSET)
    parser.add_argument('-g', '--game',
                        help="Comma-separated list of games to enumerate configs for",
                        default=UNSET,
                        nargs="*",
                        action='append')
    parser.add_argument('-o', '--options',
                        help="List of options to enumerate",
                        default=UNSET,
                        nargs='+',
                        action='append')
    parser.add_argument('-s', '--splits',
                        help="For ranges, number of sections to split range into; minimum 1, default 1",
                        default=UNSET)
    parser.add_argument('-v', '--verbose',
                        help="Verbosity; higher prints more.",
                        default=UNSET)
    parser.add_argument('-z', '--zzz',
                        help=argparse.SUPPRESS,
                        default=False,
                        action="store_true")
    args = parser.parse_args()

    # The order of arg preference: CLI > config file > defaults
    # These are the defaults
    cfg: Dict[str, Any] = {
        "dir": '.',
        "game": [],
        "options": [],
        "behavior": [],
        "splits": 1,
        "verbose": 1,
        "zzz": False,
    }

    # Typing doesn't seem to have any idea what to do with generic json
    # ... and dataclasses seem a bridge too far for an otherwise simple script...
    if args.config_file and args.config_file != UNSET and os.path.isfile(args.config_file):
        tmp_conf: Dict[str, Any] = {}
        with open(args.config_file, encoding="utf-8") as infile:
            tmp_conf = yaml.safe_load_all(infile.read())         # type: ignore

        for doc in tmp_conf:
            cfg['game'] = cfg['game'] + [doc['game']]            # type: ignore
            if 'options' in doc:
                cfg['options'].append(doc['options'])            # type: ignore
            else:
                cfg['options'].append([])
            if 'behavior' in doc:
                cfg['behavior'].append(doc['behavior'])          # type: ignore
            else:
                cfg['behavior'].append('default')

    for key in cfg:
        argval = getattr(args, key, UNSET)
        if argval != UNSET:
            # TODO: this needs massive testing
            if key in ('game', 'options'):
                cfg[key] = [val.split(',') for val in argval]
            else:
                cfg[key] = argval

    return cfg

def check_args(args: Dict[str, Any]) -> bool:
    if len(args['game']) < 1:
        print("Must supply a list of games for which to enumerate configs.")
        return False

    if len(args['options']) < 1:
        print("Must supply a list of options to enumerate for each game (enumerating all is unlikely to be what you want!).")
        return False

    if isinstance(args['splits'], int) and args['splits'] < 1:
        print("Cannot set splits to less than 1.")
        return False

    if args['zzz']:
        print("Options as parsed:")
        pprint.pprint(args)
        return False

    return True

# Using this as a method of storing our configured verbosity level so we don't have to
# pass it around. Also prepends datestamps on everything (consider making datestamp optional?).
class Debug:
    from datetime import datetime
    verbosity: int = 1

    @classmethod
    def set_verbosity(cls, verb: int = 1) -> None:
        cls.verbosity = int(verb)

    @staticmethod
    def debug_print(text: str, dbg_lvl: int = 1) -> None:
        if Debug.verbosity > dbg_lvl:
            now = Debug.datetime.now()
            print(' -- '.join([ now.strftime("%Y-%m-%d %H:%M:%S"), text ]))

def get_core_opts(game: str) -> Dict[str, Dict[str, Any]]:
    return {
        f"{game}": {
            "progression_balancing": 0,
            "accessibility": "items",
        }
    }

def get_loop_items(game: Any) -> Iterator[Tuple]:
    if 'option_definitions' in dir(game):
        yield from game.option_definitions.items()
    elif 'options_dataclass' in dir(game):
        yield from AutoWorld.AutoWorldRegister.world_types[game.game].options_dataclass.type_hints.items()

def get_splits(clival: int, confval: Union[int,str], range_start: int, range_end: int) -> int:
    splits: int = clival

    if confval != 'all':
        splits = int(confval)

    return min(splits, range_end - range_start)

def get_base_opts(opts: Dict[str, Any], game: Any, options: List[str], behavior: str='default') -> Dict[str, Any]:
    game_name: str = game.game
    base_opts: Dict[str, Any] = get_core_opts(game_name)

    for opt, cls in get_loop_items(game):
        # We'll enumerate options as part of the main process; skip them here
        Debug.debug_print(f"[get_base_opts] -- Checking for option {opt} in game {game_name}", 8)
        if opt in COMMON or opt in options:
            continue
        Debug.debug_print(f"[get_base_opts] -- Processing option {opt} for game {game_name}", 5)

        if issubclass(cls, Options.FreeText):
            Debug.debug_print(f"[get_base_opts] -- Game {game_name}: Skipping {opt}, Free Text is not supported", 3)
            continue
        if issubclass(cls, Options.TextChoice):
            Debug.debug_print(f"[get_base_opts] -- Game {game_name}: Skipping {opt}, Text Choice is not supported", 3)
            continue

        # We don't care what class they are from here, all opts seem to have a default
        if behavior == 'random':
            # built-in behavior
            base_opts[game_name][opt] = 'random'
        elif behavior == 'minimum':
            if issubclass(cls, Options.Range) or issubclass(cls, Options.NamedRange):
                base_opts[game_name][opt] = cls.range_start
            else:
                base_opts[game_name][opt] = 0
        elif behavior == 'maximum':
            if issubclass(cls, Options.Range) or issubclass(cls, Options.NamedRange):
                base_opts[game_name][opt] = cls.range_end
            else:
                base_opts[game_name][opt] = len(cls.options)
        else:
            if behavior != 'default':
                print(f"Unknown behavior '{behavior}', using default instead.")
            if isinstance(cls.default, tuple):
                base_opts[game_name][opt] = list(cls.default)
            else:
                base_opts[game_name][opt] = cls.default

    return base_opts

def calculate_radius(opts: Dict[str, Any], game: Any, options: List[str]) -> int:
    """
        Calculate the blast radius for enumerating the yamls for a given game.
        This is used to warn users if the blast radius is too large (> 1000 documents).
    """
    radius: int = 1

    for opt, cls in get_loop_items(game):
        Debug.debug_print(f"[calculate_radius] -- Checking for option {opt} in game {game.game}", 8)
        if opt in COMMON or opt not in options:
            continue
        Debug.debug_print(f"[calculate_radius] -- Processing option {opt} for game {game.game}", 5)

        Debug.debug_print(f"[calculate_radius] -- Intermediate: Blast Radius is {radius} for {game.game}", 3)

        if issubclass(cls, Options.Toggle) or issubclass(cls, Options.DefaultOnToggle):
            radius *= 2

        elif issubclass(cls, Options.Choice):
            if options[opt] == "all":
                radius *= len(cls.options)
            else:
                radius *= len(options[opt])

        elif issubclass(cls, Options.Range) or issubclass(cls, Options.NamedRange):
            radius *= get_splits(opts['splits'], options[opt], cls.range_start, cls.range_end) + 1

            if issubclass(cls, Options.NamedRange):
                radius *= len(cls.special_range)

    Debug.debug_print(f"[calculate_radius] -- Returning blast radius {radius} for {game.game}", 3)
    return radius

# This is what does the heavy lifting.
def enumerate_yaml(opts: Dict[str, Any], game: Any, base: Dict[str, Any],
                   instance: Dict[str, Any], options: List[str]) -> Iterator[Dict[str,Any]]:
    """
        Enumerate the YAMLs by doing "yield from" recursively, then yielding at the last step.
    """
    game_name: str = game.game
    new_instance: Dict[str, Any] = copy.deepcopy(instance)

    # Whether we need to yield a single item (which gets sent back) or recurse again
    last_call: bool = len(base[game_name])+len(options)-1 == len(instance[game_name])
    Debug.debug_print(f"[enumerate_yaml] -- last call is {last_call}", 4)

    for opt, cls in get_loop_items(game):
        Debug.debug_print(f"[enumerate_yaml] -- Checking for option {opt} in game {game_name}", 8)
        if opt in COMMON or opt in instance[game_name] or opt not in options:
            continue
        Debug.debug_print(f"[enumerate_yaml] -- Processing option {opt} in game {game_name}", 5)

        if issubclass(cls, Options.Toggle) or issubclass(cls, Options.DefaultOnToggle):
            Debug.debug_print(f"[enumerate_yaml] -- option {opt} is a toggle", 4)
            for val in range(2):
                new_instance[game_name][opt] = val
                if last_call:
                    yield new_instance
                else:
                    yield from enumerate_yaml(opts, game, base, new_instance, options)

        elif issubclass(cls, Options.Choice):
            Debug.debug_print(f"[enumerate_yaml] -- option {opt} is a choice", 4)
            for choice, val in cls.options.items():
                if options[opt] != 'all' and choice not in options[opt]:
                    continue
                new_instance[game_name][opt] = val
                if last_call:
                    yield new_instance
                else:
                    yield from enumerate_yaml(opts, game, base, new_instance, options)

        elif issubclass(cls, Options.Range) or issubclass(cls, Options.NamedRange):
            Debug.debug_print(f"[enumerate_yaml] -- option {opt} is a range", 4)
            splits: int = get_splits(opts['splits'], options[opt], cls.range_start, cls.range_end)
            Debug.debug_print(f"[enumerate_yaml] -- using splits: {splits}", 4)
            value: float = cls.range_start
            while value <= cls.range_end:
                new_instance[game_name][opt] = round(value)
                if last_call:
                    yield new_instance
                else:
                    yield from enumerate_yaml(opts, game, base, new_instance, options)
                value += (cls.range_end - cls.range_start) / splits

            if issubclass(cls, Options.NamedRange):
                Debug.debug_print(f"[enumerate_yaml] -- option {opt} is a /special/ range", 4)
                for val in cls.special_range:
                    new_instance[game_name][opt] = val
                    if last_call:
                        yield new_instance
                    else:
                        yield from enumerate_yaml(opts, game, base, new_instance, options)

def write_yaml(out_yaml: Any, counter: int, game_name: str, raw_game_name: str, yml: Dict[str, Any]) -> None:
    if counter > 1:
        out_yaml.write("---\n")
    out_yaml.write("\n")
    out_yaml.write(f"name: {game_name[0:12]}{counter}\n")
    out_yaml.write(f"description: {raw_game_name} - {counter}\n")
    out_yaml.write(f"game: {raw_game_name}\n")
    out_yaml.write(yaml.dump(yml))
    out_yaml.write("\n")

def hyper_enumerator() -> None:
    opts: Dict[str, Any] = parse_opts()
    Debug.set_verbosity(opts['verbose'])
    Debug.debug_print(f"[main] -- set verbosity to {Debug.verbosity}", 3)

    if not check_args(opts):
        sys.exit(0)

    processed: List[str] = []
    processing: int = 0
    for cls in AutoWorld.AutoWorldRegister.world_types.values():
        Debug.debug_print(f"[main] -- Checking if we want to process game {cls.game}", 8)
        if cls.game not in opts['game']:
            continue
        Debug.debug_print(f"[main] -- Processing game {cls.game}", 2)
        for gameno in range(len(opts['game'])):
            if opts['game'][gameno] == cls.game:
                processing = gameno
                break
        Debug.debug_print(f"[main] -- game is number {gameno}", 4)
        base: Dict[str, Any] = get_base_opts(opts, cls, opts['options'][processing], opts['behavior'][processing])
        instance: Dict[str, Any] = get_base_opts(opts, cls, opts['options'][processing], opts['behavior'][processing])

        blast_radius: int = calculate_radius(opts, cls, opts['options'][processing])
        if blast_radius > 1000:
            print(f"Enumerating the YAMLs for {cls.game} would be large: {blast_radius}")
            answer: str = input("Are you sure you want to proceed? [y/N] ")
            if answer.lower() not in ["y","yes"]:
                continue

        counter: int = 0
        game_name: str = '_'.join(cls.game.split())
        # TODO: figure out why we're getting dupes (and remove them)
        cache: Dict[str, int] = {}
        try:
            with open(os.path.join(opts['dir'], f"{game_name}.yaml"), 'w', encoding="utf-8") as out_yaml:
                for yml in enumerate_yaml(opts, cls, base, instance, opts['options'][processing]):
                    if json.dumps(yml, sort_keys=True) in cache:
                        continue
                    cache[json.dumps(yml, sort_keys=True)] = 1
                    counter += 1
                    write_yaml(out_yaml, counter, game_name, cls.game, yml)
        except IOError as error:
            print(f"Unable to open {game_name}.yaml for writing in directory {opts['dir']}:")
            print(f"Error number {error.errno} -- {error}")
            continue

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

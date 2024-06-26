# AP-YAML-Enumerator
A script to enumerate combinations of options for AP games; useful for testing.

It will generate a yaml file per game. Each yaml file will be full of a document per combination of options.

As an example of how explosive this can be:
If you select 4x options that each have 3x possibilities, then you should see 81 output documents in a single yaml file.
The example config shows an ALTTP example with similar numbers (54). The number of yamls can quickly get out of hand, be warned.
If the number of documents for a game would be > 1000, a warning will ask the user to continue in case that's more
than they expected.

# How to run

Copy the script into your Archipelago directory and run it:  
`python3 aye.py --config <path to config> --dir <output dir>`

# How to configure

The easiest method of configuration is to create a yaml file with a document per game you'd like to generate files for.
See the example config as a starting point.

List the options you'd like to have enumerated, and you can limit the options to shrink your generated number of yamls.

For example, if you want to limit the goal in ALTTP, you can set:
```
goal: [ ganon, triforce_hint ]
```

### game sections

options -- each option you'd like to see enumerated. You can set each option to "all" if you don't otherwise
have a specific limitation in mind. Ranges are limited by setting the number of "splits" that you'd like to see.
See more about splits below.

behavior -- This defines the behavior for options that aren't being enumerated. The others can be any of:  
- default
- random
- minimum
- maximum

### About splits

The way ranges are limited is by specifying how many sections you'd like to see. The minimum and default value is "1", which
has 2x definitive boundaries: the minimum and maximum for the range. So selecting a single "split" is the same as specifying
that you only want to use the minimum and maximum values.

Generally the number of values selected for ranges is 1 + the number of "splits" specified. So if you select 4 splits, then
you should see minimum, intermediate 1, middle, intermediate 2, and maximum (5x values) as the values specified. Math will
be used to choose all values.

If more splits are specified than can possibly exist (e.g. 10 for crystals to open Ganon's Tower in ALTTP), then the max
number of splits will be reduced to whatever is allowed for a given option. This allows setting generic --splits on command
line and not having to worry about it breaking smaller ranges.

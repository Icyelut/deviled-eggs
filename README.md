# deviled-eggs
Tools for preserving the Project EGG files

## Downloading

Downloading is done with the `download` subcommand.
This will ask you for your ProjectEGG account username and password.
```
python main.py download <path\to\download\destination>
```

If you already have the metadata file `data.json`, then you can pass the path with 

```
python main.py download --server_json <path\to\data.json> <path\to\download\destination>
```

You do not need an account to download via the `data.json` file, but it may be out of date!

If you run the command again, it will only download new or missing files.

## Preparing the romanization file

Use the `romanize` subcommand to generate `missing_romanizations.csv`
```
python main.py romanize <path\to\data.json> <path\to\output\to>
```

Rename it and add a `romanized` column before feeding it back in to check your progress:
```
python main.py romanize --romanized_csv <path\to\romanization.csv> <path\to\data.json> <path\to\output\to>
```

This time, unless the data.json has been updated, `missing_romanizations.csv` will be empty.
You will get warnings for blank romanizations or duplicate entries.
```
Product ID 1812 is in the romanization CSV but the romanization is blank
Product ID 13 has 2 dupe(s) in the romanization CSV
```


## Generating dat files
To run the datting process, use the `dat` subcommand:

```
python main.py dat \
<dumper's name> <path\to\download\destination> <path\to\data.json> <path\to\romanization.csv> <path\to\output\to>
```

## dat generation logic

### Parent/clone selection

Two or more archives are considered clones of each other if the archive title is identical (whoa).
The parent is the one with the lower `digital_serial` (== `productId`)

This logic is simple because it occurs last, after all the archives have been created.
See the archive selection logic to understand more.

# deviled-eggs
Tools for preserving the Project EGG files

## Downloading

Downloading is done with the `download` subcommand.
This will ask you for your ProjectEGG account username and password.
```
python main.py download <path\to\download\destination>
```

You can specifiy username and password in advance.
```
python main.py download --user <username> --pw <password> <path\to\download\destination>
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

### Archive selection

An `egg` will be associated with an archive if:
1. It has files associated with it that were detected during the file hashing phase
2. There are no newer releases of that egg that are identical to it

An egg is determined to be a newer release of the current egg if it's `productId` is larger and these fields are identical:
1. `region`
2. `platform`
3. `gameFilename`
4. `manualFilename`
5. `musicFilename`

Furthermore, there is a check to see if this is simply a dummy egg used for showing an English store page.
These dummy eggs have the same game/music/manual files as their base Japanese game, and therefore are out of scope for datting.
An egg is determined to be a dummy if it is region 1 and has no unique files of it's own.

The archive number is simply sequential by processing order, which is determined by sorting productId ascending.

### Revision determination

Multiple eggs are considered revisions of each other if the set {game_filename, manual_filename, music_filename} is different while the following fields are identical:
1. `region`
2. `platform`
3. `title`

Revision 0 is the egg with the lowest `productId`, rev 1 is the next highest, etc.

### Region determination

An archive will be marked as `World` if
1. It's a region 1 (English/World) egg
2. It's a region 0 (Japan) egg with exactly one egg in another region (determined by having identical files)

An archive will be marked as `Unknown` if
1. It's a region 0 egg with multiple eggs in other regions
2. It has a region that is not 0 or 1

The purpose of the `Uknown` region is simply to alert the datter that an easy determination can't be made and human attention is needed.

If an archive is not marked as `World` or `Uknown`, it will be marked as `Japan`.


### Parent/clone selection

Two or more archives are considered clones of each other if the archive title is identical (whoa).
The parent is the one with the lower `digital_serial` (== `productId`)

This logic is simple because it occurs last, after all the archives have been created.
See the archive selection logic to understand more.

### Other attributes

#### `d_date` (dump date)

Pulled from the `date` header from the HTML response headers of the game file.

#### `digital_serial1`

Set to the `productID`

#### `additional`

Set to the value of the `platform` egg field

### Anomalies

#### Filename discrepancies

There are some files that have filenames in the metadata that don't match the filenames in CDN.
For datting purposes, these are hardcoded in to link the metadata to the CDN filename without need to modify the metadata, and the CDN filename is used in the DAT.
A comment is left in the `comment2` field: `Server JSON incorrectly names this as <metadata filename>`

| Metadata Filename | Actual (CDN) Filename |
| ----------------- | --------------------- |
| ECOM3005.bin      | COM3005a.bin          |
| COM3008.bin       | COM3008a.bin          |


#### Missing files

These files were not available when this effort began, and are thus completely MIA at this time.

| Filename          | `productId` | Title                                                         |
| ----------------- | ----------- | -----------                                                   |
| STW1003a.bin      | 173         | Shiro to Kuro no Densetsu - Hyakki-hen (Ongaku Data nomi)     
| BOT3008a.bin      | 765         | T.N.T.                                                        
| SKP0011m.bin      | 1044        | Ironclad
| COM5032a.bin      | 1264, 1265  | Jino-Brodiaea's Wander Number, After Devil Force Gaiden - The Sword Battle of Quada 
| COM5032m.bin      | 1264, 1265  | Jino-Brodiaea's Wander Number, After Devil Force Gaiden - The Sword Battle of Quada 
| COM5033a.bin      | 1266        | Gensei Haiyuuki
| COM5033m.bin      | 1266        | Gensei Haiyuuki
| COM5034a.bin      | 1267        | DEVIL FORCE III: Ken to Hanataba
| COM5034m.bin      | 1267        | DEVIL FORCE III: Ken to Hanataba
| COM5035a.bin      | 1268        | After Devil Force - Kyou-ou no Koukeisha
| COM5035m.bin      | 1268        | After Devil Force - Kyou-ou no Koukeisha
| COM5036a.bin      | 1269        | Geo Conflict 3 - Hell's Gate Crusaders
| COM5036m.bin      | 1269        | Geo Conflict 3 - Hell's Gate Crusaders
| COM5038a.bin      | 1270        | Daikaisen
| COM5038m.bin      | 1270        | Daikaisen
| COM5039a.bin      | 1271        | Quiz Tsunahiki Champ
| COM5039m.bin      | 1271        | Quiz Tsunahiki Champ
| COM5040a.bin      | 1272        | Poly Poly! Speed Daisakusen
| COM5040m.bin      | 1272        | Poly Poly! Speed Daisakusen
| ETG0008a.bin      | 1833        | Sword Dancer – Kyoujin no Megami                                                        
| ETG0008m.bin      | 1833        | Sword Dancer – Kyoujin no Megami


#### 404 files

Some files just give us 404's when we try to download them now.
They belong to project pages that no longer exist.
At this time, this list matches the missing file list above.

| Filename          | `productId` |
| ----------------- | ----------- |
| STW1003a.bin      | 173         |
| BOT3008a.bin      | 765         |
| SKP0011m.bin      | 1044        |
| COM5032a.bin      | 1264, 1265  |
| COM5032m.bin      | 1264, 1265  |
| COM5033a.bin      | 1266        |
| COM5033m.bin      | 1266        |
| COM5034a.bin      | 1267        |
| COM5034m.bin      | 1267        |
| COM5035a.bin      | 1268        |
| COM5035m.bin      | 1268        |
| COM5036a.bin      | 1269        |
| COM5036m.bin      | 1269        |
| COM5038a.bin      | 1270        |
| COM5038m.bin      | 1270        |
| COM5039a.bin      | 1271        |
| COM5039m.bin      | 1271        |
| COM5040a.bin      | 1272        |
| COM5040m.bin      | 1272        |
| ETG0008a.bin      | 1833        |
| ETG0008m.bin      | 1833        |

# Credits

- **Eintei**: all the original reverse engineering and documentation that made this possible
- **luigi auriemma**: the original data.json download script, which was incorporated into this one
- **Bestest**: coordination and leadership for the official preservation effort, reverse engineering
- **Hiccup**: datting support and advice
- **proffrink**: scraping, research
- **Shadów**: reverse engineering
- **Icyelut** (me): this script, romanization

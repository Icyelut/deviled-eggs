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

## Generating dat files
To run the datting process, use the `dat` subcommand:

```
python main.py dat <dumper's name> <path\to\download\destination> <path\to\data.json> <path\to\download\destination> .
```

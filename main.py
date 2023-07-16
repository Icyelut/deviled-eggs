import argparse
import os.path
import pathlib
from random import randint
import shutil
import sys
import csv
import json
import time
from io import StringIO
from os import SEEK_END
from urllib.parse import unquote_plus
from itertools import islice
import http.cookiejar

import pytz
import datetime
from xml.etree.ElementTree import ElementTree

import requests
from requests.exceptions import HTTPError
import xmlschema
from xmlschema import XMLSchema

import tools.hash_utils


# Options downloading the server JSON
USER_AGENT = 'c384da2W9f73dz20403d'
USE_SERVER_RESPONSE_FILE = False


def is_valid_new_file_location(file_path):
    path_maybe = pathlib.Path(file_path)
    path_resolved = None

    # try and resolve the path
    try:
        path_resolved = path_maybe.resolve(strict=False).expanduser()

    except Exception as e:
        raise argparse.ArgumentTypeError("Failed to parse `{}` as a path: `{}`".format(file_path, e))

    if not path_resolved.parent.exists():
        raise argparse.ArgumentTypeError("The parent directory of `{}` doesn't exist!".format(path_resolved))

    return path_resolved


def is_file(strict=True):
    def _is_file(file_path):

        path_maybe = pathlib.Path(file_path)
        path_resolved = None

        # try and resolve the path
        try:
            path_resolved = path_maybe.resolve(strict=strict).expanduser()

        except Exception as e:
            raise argparse.ArgumentTypeError("Failed to parse `{}` as a path: `{}`".format(file_path, e))

        # double check to see if its a file
        if strict:
            if not path_resolved.is_file():
                raise argparse.ArgumentTypeError("The path `{}` is not a file!".format(path_resolved))

        return path_resolved

    return _is_file


def find_missing_romanizations(server_json, csv_lines):
    missing_romanizations = []
    for egg in server_json:
        title_eng = [x for x in csv_lines if x["productId"] == egg["productId"]]
        if len(title_eng) == 0:
            print("Product ID {} is present in the server JSON but not the romanization CSV".format(egg["productId"]))
            missing_romanizations.append(egg)
        elif len(title_eng) > 1:
            print("Product ID {} has {} dupe(s) in the romanization CSV".format(egg["productId"], len(title_eng) - 1))
        else:
            title_eng = title_eng[0]
            if title_eng["romanized"].strip() == "":
                print("Product ID {} is in the romanization CSV but the romanization is blank".format(egg["productId"]))

    if len(missing_romanizations) > 0:
        with open("missing_romanizations.csv", "w", encoding="utf8", newline='') as csvfile:
            writer = csv.DictWriter(csvfile, delimiter=",", quotechar='"', fieldnames=server_json[0].keys())
            writer.writeheader()
            writer.writerows(missing_romanizations)


def find_newer_releases_by_file(filename, server_json, egg, filename_key):
    if filename == "":
        return []

    return [x for x in server_json if
            int(x["productId"]) > int(egg["productId"]) and x[filename_key] == filename and x["region"] == egg[
                "region"]]


def find_newer_releases_by_files(game_filename, manual_filename, music_filename, server_json, egg):
    if game_filename == "" and manual_filename == "" and music_filename == "":
        return []

    return [x for x in server_json if
            int(x["productId"]) > int(egg["productId"])
            and x["region"] == egg["region"]
            and x["platform"] == egg["platform"]
            and x["gameFilename"] == game_filename
            and x["manualFilename"] == manual_filename
            and x["musicFilename"] == music_filename]


def has_newer_releases(game_filename, manual_filename, music_filename, server_json, egg):
    newer_releases_list = find_newer_releases_by_files(game_filename, manual_filename, music_filename, server_json, egg)

    return len(newer_releases_list) > 0

def find_revisions(game_filename, manual_filename, music_filename, server_json, egg):
    # If the title, system, and region are the same and have a different combination of {game, manual, music}
    # then it's a revision
    if game_filename == "" and manual_filename == "" and music_filename == "":
        return []

    return [x for x in server_json if
            int(x["productId"]) != int(egg["productId"])
            and x["region"] == egg["region"]
            and x["platform"] == egg["platform"]
            and x["title"] == egg["title"]
            and {x["gameFilename"], x["manualFilename"], x["musicFilename"]} !=
            {game_filename, manual_filename, music_filename}]


def what_revision(egg, revisions):
    sorted_revisions = sorted(revisions, key=lambda y: y["productId"])
    for x, compare_egg in enumerate(sorted_revisions):
        if int(compare_egg["productId"]) < int(egg["productId"]):
            return x + 1

    return 0


def find_english_releases_for_file(filename, server_json, egg, filename_key):
    if filename == "":
        return []
    return [x for x in server_json if
            x["productId"] != egg["productId"] and x[filename_key] == filename and x[
                "region"] != 0]


def find_jpn_releases_for_file(filename, server_json, egg, filename_key):
    if filename == "":
        return []
    return [x for x in server_json if
            x["productId"] != egg["productId"] and x[filename_key] == filename and x[
                "region"] == 0]


def find_english_releases(game_filename, manual_filename, music_filename, server_json, egg):
    english_releases = find_english_releases_for_file(game_filename, server_json, egg, "gameFilename") \
                       + find_english_releases_for_file(manual_filename, server_json, egg, "manualFilename") \
                       + find_english_releases_for_file(music_filename, server_json, egg, "musicFilename")

    return english_releases


def find_japanese_releases(game_filename, manual_filename, music_filename, server_json, egg):
    jpn_releases = find_jpn_releases_for_file(game_filename, server_json, egg, "gameFilename") \
                   + find_jpn_releases_for_file(manual_filename, server_json, egg, "manualFilename") \
                   + find_jpn_releases_for_file(music_filename, server_json, egg, "musicFilename")

    return jpn_releases


def has_unique_files(game_filename, manual_filename, music_filename, server_json, egg):
    unique_game_file = game_filename != "" and find_jpn_releases_for_file(game_filename, server_json, egg, "gameFilename") == 0
    unique_manual_file = manual_filename != "" and find_jpn_releases_for_file(manual_filename, server_json, egg, "manualFilename") == 0
    unique_music_file = music_filename != "" and find_jpn_releases_for_file(music_filename, server_json, egg, "musicFilename") == 0

    return unique_game_file or unique_manual_file or unique_music_file


def get_dump_date_from_headers(filename, header_files_dict):
    dump_date_epoch = get_access_date_as_epoch(header_files_dict[filename])
    dump_date = datetime.datetime.fromtimestamp(dump_date_epoch).astimezone().strftime('%Y-%m-%d')

    return dump_date


def assemble_file_dat_info(filename, header_files_dict, files_hashes_dict, filter_str):
    headers = get_dict_from_http1(header_files_dict[filename])
    target_file = files_hashes_dict[filename]

    if "last-modified" in headers.keys():
        last_modified = headers["last-modified"]
    else:
        last_modified = ""

    if "content-length" in headers.keys():
        content_length = headers["content-length"]

        if int(content_length) != target_file["size"]:
            print(f"[WARNING] File size ({content_length}) doesn't match content-length header ({target_file['size']}) for {filename}")

    return {
        "@forcename": filename,
        "@forcescenename": "",
        "@emptydir": 0,
        "@extension": "",
        "@item": "",
        "@date": "",
        "@format": "Default",
        "@note": "",
        "@filter": filter_str,
        "@version": "",
        "@update_type": "",
        "@size": f'{target_file["size"]}',
        "@crc32": f'{target_file["crc32"]}',
        "@md5": f'{target_file["md5"]}',
        "@sha1": f'{target_file["sha1"]}',
        "@sha256": f'{target_file["sha256"]}',
        "@serial": "",
        "@header": "",
        "@bad": 0,
        "@mia": 0,
        "@unique": 1,
        "@mergename": "",
        "@unique_attachment": "",
    }

def find_parent(game_files, egg):
    results = [x for x in game_files if
               x["archive"]["@name"] == egg["@name"]]

    # The parent is the egg that was released first
    earliest = min(results, key=lambda x: int(x["source"][0]["serials"]["@digital_serial1"]), default=None)
    if earliest is not None and earliest["source"][0]["serials"]["@digital_serial1"] == egg["source"][0]["serials"]["@digital_serial1"]:
        # This egg is the parent, so return None
        earliest = None

    return earliest


def assign_parent_clone(game_files):

    for game in game_files:
        parent_egg = find_parent(game_files, game)

        if parent_egg is not None:
            game["archive"]["@clone"] = parent_egg["archive"]["@number"]
        else:
            game["archive"]["@clone"] = "P"





def assemble_file_info(server_json, csv_lines, files_hashes_dict, dumper, header_files_dict):
    missing = []
    combined = []

    server_json = sorted(server_json, key=lambda y: int(y["productId"]))

    for idx, egg in enumerate(server_json, start=1):

        game_filename = egg["gameFilename"]
        music_filename = egg["musicFilename"]
        manual_filename = egg["manualFilename"]

        if game_filename == 'COM3008.bin':
            game_filename = 'COM3008a.bin'
            comment2 = "Server JSON incorrectly names this as COM3008.bin\n"
        elif game_filename == "ECOM3005a.bin":
            game_filename = "COM3005a.bin"
            comment2 = "Server JSON incorrectly names this as ECOM3005a.bin\n"
        else:
            comment2 = ""

        file_dat_info = []
        for filen in [("game", game_filename), ("music", music_filename), ("manual", manual_filename)]:
            if filen[1] != "":
                if filen[1] in files_hashes_dict.keys():
                    file_dat_info.append(
                        assemble_file_dat_info(filen[1], header_files_dict, files_hashes_dict, filen[0]))
                else:
                    print("WARNING: Could not find hashes for file '{}'".format(filen[1]))
                    missing.append(egg)

        if len(file_dat_info) == 0:
            print(f"WARNING: archive for product id {egg['productId']} has no dattable files, skipping...")
            continue

        if has_newer_releases(game_filename, manual_filename, music_filename, server_json, egg):
            # Don't use older releases of a game
            print(f"WARNING: product id {egg['productId']} has newer releases, skipping...")
            continue

        revisions = find_revisions(game_filename, manual_filename, music_filename, server_json, egg)

        if len(revisions):
            revision_num = what_revision(egg, revisions)
        else:
            revision_num = 0

        if revision_num != 0:
            revision_string = f"Rev {revision_num}"
        else:
            revision_string = ""

        english_releases = find_english_releases(game_filename, manual_filename, music_filename, server_json, egg)

        if egg["region"] == 1:
            japanese_releases = find_japanese_releases(game_filename, manual_filename, music_filename, server_json, egg)
            if len(japanese_releases) > 0:
                for release in japanese_releases:
                    print(
                        f"Found English page (id={egg['productId']}) of Japanese (id={release['productId']})")

                if not has_unique_files(game_filename, manual_filename, music_filename, server_json, egg):
                    print(f"INFO: English release product id={egg['productId']}) has no unique files compared to Japanese releases, skipping...")
                    continue
            else:
                print(f"Found region 1 release without a region 0 release: id={egg['productId']}")

            region = "World"
        elif egg["region"] == 0 and len(english_releases) == 1:
            region = "World"
        elif egg["region"] == 0 and len(english_releases) == 0:
            region = "Japan"
        elif egg["region"] == 0 and len(english_releases) > 1:
            for release in english_releases:
                print(
                    f"WARNING: Found region 0 release id={egg['productId']} with multiple ({len(english_releases)}) non-Japan releases: {release['productId']}")
            region = "Unknown"
        else:
            print(f"WARNING: Found unknown region {egg['region']} for id={egg['productId']}")
            region = "Unknown"

        platform = egg["platform"]
        if platform == "アーケード":
            platform = "Arcade"
        elif platform == "メガドライブ":
            platform = "Mega Drive"
        elif platform == "PCエンジン":
            platform = "PC Engine"
        elif platform == "その他":
            platform = "Other"

        if egg["genre"] == "ETC":
            category = ""
        else:
            category = "Games"

        dump_date = get_dump_date_from_headers(game_filename, header_files_dict)

        romanization_dict_list = [x for x in csv_lines if x["productId"] == egg["productId"]]

        if len(romanization_dict_list) == 0:
            print(f"ERROR: Missing romanization for productId {egg['productId']}")
            raise ValueError(f"ERROR: Missing romanization for productId {egg['productId']}")

        romanization_dict = romanization_dict_list[0]


        number = f"{idx:04}"

        details = {
            "@section": "Trusted Dump",
            "@rominfo": "",
            "@d_date": f"{dump_date}",
            "@d_date_info": 1,
            "@r_date": "",
            "@r_date_info": 0,
            "@dumper": f"{dumper}",
            "@project": "No-Intro",
            "@originalformat": "",
            "@nodump": 0,
            "@tool": "deviled-eggs v1.0",
            "@origin": "",
            "@comment1": "",
            "@comment2": f"{comment2}",
            "@link1": "",
            "@link1_public": 0,
            "@link2": "",
            "@link2_public": 0,
            "@link3": "",
            "@link3_public": 0,
            "@region": region,
            "@media_title": "",
        }
        source = [{"details": details,
                   "serials": {
                       "@media_serial1": "",
                       "@media_serial2": "",
                       "@media_serial3": "",
                       "@pcb_serial": "",
                       "@romchip_serial1": "",
                       "@romchip_serial2": "",
                       "@savechip_serial": "",
                       "@chip_serial": "",
                       "@mediastamp": "",
                       "@box_barcode": "",
                       "@digital_serial1": egg["productId"],
                       "@digital_serial2": ""},
                   "file": file_dat_info
                   }]
        archive = {
            "@number": number,
            "@clone": "P",
            "@regparent": "",
            "@mergeof": "",
            "@mergename": "",
            "@name": f"{romanization_dict['romanized'].replace('　', ' ').replace('  ', ' ').replace('–', '-').replace('–', '-')}",
            "@name_alt": f"{egg['title'].replace('　', ' ').replace('  ', ' ').replace('–', '-').replace('–', '-')}",
            "@region": region,
            "@languages": "Ja",
            "@showlang": 0,
            "@langchecked": "no",
            "@version": revision_string,
            "@devstatus": "",
            "@additional": f"{platform}",
            "@special1": "",
            "@special2": "",
            "@alt": 0,
            #"@gameid": f'{egg["productId"]}', #Hiccup says NO to gameid
            "@description": "",
            "@bios": 0,
            "@licensed": 1,
            "@pirate": 0,
            "@physical": 0,
            "@complete": 1,
            "@adult": 0,
            "@dat": 1,
            "@listed": 1,
            "@sticky_note": "",
            "@datter_note": "",
            "@categories": category
        }

        new_dict = {"@name": f"{romanization_dict['romanized']}",
                    "archive": archive,
                    "source": source,
                    }
        combined.append(new_dict)

    if len(missing) > 0:
        with open("missing.csv", "w", encoding="utf8", newline='') as csvfile:
            writer = csv.DictWriter(csvfile, delimiter=",", quotechar='"', fieldnames=server_json[0].keys())
            writer.writeheader()
            writer.writerows(missing)

    return combined


def chunk(it, size):
    it = iter(it)
    return iter(lambda: tuple(islice(it, size)), ())


def generate_split_xml(filename, files_list):
    # Just do some guesswork since we don't know how large the file will be until it's already written
    archive_limit = 500
    chunk_iter = chunk(files_list, archive_limit)
    for idx, chunk_item in enumerate(chunk_iter):
        basename = filename.split(".xml")[0]
        new_name = f"{basename}_{idx}.xml"
        generate_xml(new_name, chunk_item)


def generate_xml(filename, files_list):
    print(f"Writing {filename}...")
    json_str = json.dumps({"game": files_list})

    schema = xmlschema.XMLSchema('example_upload_custom.xsd.xml')
    xml_ = xmlschema.from_json(json_str, schema=schema)
    ElementTree(xml_).write(filename)


def generate_game_xml(game_files):
    timenow = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    generate_split_xml(f'games_{timenow}.xml', game_files)


def crosscheck_files(game_dat_list, file_list):
    just_the_filenames = [y["@forcename"] for x in game_dat_list for y in x["source"][0]["file"]]
    for f in file_list:
        if f not in just_the_filenames:
            print(f"WARNING: {f} is missing from the final dat!")


def create_individual_json(files_list, server_json):
    os.makedirs(".\\json", exist_ok=True)
    result_list_for_csv = []
    for file in files_list:
        archive_no = file["archive"]["@number"]
        product_id = file["source"][0]["serials"]["@digital_serial1"]
        for egg in server_json:
            if egg['productId'] == product_id:
                json_str = json.dumps(egg)
                filename = f".\\json\\{archive_no}.json"
                with open(filename, "w") as outfile:
                    outfile.write(json_str)

                result_list_for_csv.append((archive_no, f"{archive_no}.json"))

    return result_list_for_csv


def dat(parsed_args):
    schema = xmlschema.XMLSchema('example_upload_custom.xsd.xml')
    XMLSchema.meta_schema.validate('example_upload_custom.xsd.xml')

    print("Reading romanization CSV...")
    csv_lines = None
    with open(parsed_args.romanized_csv, encoding="utf8") as csvfile:
        reader = csv.DictReader(csvfile, delimiter=",", quotechar='"')
        csv_lines = [x for x in reader]

    print(f"Reading server JSON {parsed_args.server_json}...")
    server_json = json.loads(open(parsed_args.server_json, encoding="utf8").read())

    print("Checking for missing romanizations...")
    find_missing_romanizations(server_json, csv_lines)

    print("Hashing files...")
    files_hashes = tools.hash_utils.hash_directory(str(parsed_args.cdn_dir), include_re=r"\.bin$")
    files_hashes_dict = {}
    header_files_dict = {}
    for x in files_hashes:
        files_hashes_dict[x[0]] = {"filename": x[0], "size": x[1], "crc32": x[2], "md5": x[3], "sha1": x[4], "sha256": x[5]}
        header_files_dict[x[0]] = os.path.join(parsed_args.cdn_dir, f"{x[0]}_headers.txt")

    timenow = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    with open(f"hashes_{timenow}.csv", "w", encoding="utf8", newline='') as csvfile:
        writer = csv.DictWriter(csvfile, delimiter=",", quotechar='"', fieldnames=["filename", "size", "crc32", "md5", "sha1", "sha256"])
        writer.writeheader()

        writer.writerows(files_hashes_dict.values())

    print("Compiling dump info...")
    game_files = assemble_file_info(server_json, csv_lines, files_hashes_dict, parsed_args.dumper, header_files_dict)


    print("Assigning parent/clone relationships...")
    assign_parent_clone(game_files)

    print("Generating DATs...")
    generate_game_xml(game_files)

    print("Making sure all files have been datted...")
    crosscheck_files(game_files, [x[0] for x in files_hashes])

    print("Generating individual JSON files...")
    json_list = create_individual_json(game_files, server_json)

    print("Generating JSON CSV...")

    with open(f"json_{timenow}.csv", "w", encoding="utf8", newline='') as csvfile:
        writer = csv.DictWriter(csvfile, delimiter=",", quotechar='"', fieldnames=["archive", "json file"])
        writer.writeheader()

        files = [{"archive": x[0], "json file": x[1]} for x
                 in json_list]

        writer.writerows(files)

    print("Generating headers CSV...")

    with open(f"headers_{timenow}.csv", "w", encoding="utf8", newline='') as csvfile:
        writer = csv.DictWriter(csvfile, delimiter=",", quotechar='"', fieldnames=["filename", "header file"])
        writer.writeheader()

        files = [{"filename": pathlib.Path(x[0]).name, "header file": pathlib.Path(header_files_dict[x[0]]).name} for x
                 in files_hashes]

        writer.writerows(files)


    print("Done")


def romanize(parsed_args):
    print("Reading romanization CSV...")
    csv_lines = None
    with open(parsed_args.romanized_csv, encoding="utf8") as csvfile:
        reader = csv.DictReader(csvfile, delimiter=",", quotechar='"')
        csv_lines = [x for x in reader]

    print(f"Reading server JSON {parsed_args.server_json}...")
    server_json = json.loads(open(parsed_args.server_json, encoding="utf8").read())

    print("Checking for missing romanizations...")
    find_missing_romanizations(server_json, csv_lines)


def generate_file_list(json_file):
    print(f"Reading server JSON {os.path.basename(json_file)}...")
    server_json = json.loads(open(json_file, encoding="utf8").read())

    file_list = {egg["gameFilename"] for egg in server_json if egg["gameFilename"] != ""} | \
                {egg["musicFilename"] for egg in server_json if egg["musicFilename"]} | \
                {egg["manualFilename"] for egg in server_json if egg["manualFilename"]}

    file_list = [x for x in file_list]
    for idx, x in enumerate(file_list):
        if x == "ECOM3005.bin":
            file_list[idx] = "COM3005a.bin"
        elif x == "COM3008.bin":
            file_list[idx] = "COM3008a.bin"

    file_list.sort()

    return file_list


def convert_last_modified_str(timestr):
    d = datetime.datetime.strptime(timestr, '%a, %d %b %Y %H:%M:%S %Z')
    local = pytz.timezone("GMT")
    local_dt = local.localize(d, is_dst=None)
    last_modified_epoch = int(local_dt.timestamp())

    return last_modified_epoch


def get_dict_from_http1(header_filepath):
    headers = requests.structures.CaseInsensitiveDict()
    with open(header_filepath, mode="r", newline="\r\n", encoding="utf8") as f:
        for line in f:
            if ":" in line:
                line_split = line.split(":", maxsplit=1)
                field = line_split[0].strip()
                value = line_split[1].strip()
                headers[field] = value

    return headers


def get_last_modified_as_epoch(header_filepath):
    headers = get_dict_from_http1(header_filepath)

    last_modified = headers["last-modified"]
    last_modified_epoch = convert_last_modified_str(last_modified)

    return last_modified_epoch


def get_access_date_as_epoch(header_filepath):
    headers = get_dict_from_http1(header_filepath)

    last_modified = headers["date"]
    last_modified_epoch = convert_last_modified_str(last_modified)

    return last_modified_epoch


def check_for_older_headers(new_headers, filepath, header_filepath):
    try:
        last_modified_epoch = get_last_modified_as_epoch(header_filepath)
    except KeyError:
        # No last-modified header
        print("\nNo last-modified")
        return True
    except FileNotFoundError:
        # Headers don't exist (the file has probably never been downloaded)
        return True

    if "last-modified" in new_headers.keys():
        new_last_modified_epoch = convert_last_modified_str(new_headers["last-modified"])
    else:
        # No last-modified header
        return True

    return last_modified_epoch < new_last_modified_epoch


def move_older_file(filepath, header_filepath):
    if not os.path.exists(header_filepath):
        return False
    print("Found older file, moving...")
    try:
        last_modified_epoch = get_last_modified_as_epoch(header_filepath)
        new_folder = os.path.join(pathlib.Path(filepath).parent, f'{pathlib.Path(filepath).name}_{last_modified_epoch}')
    except KeyError:
        last_modified_epoch = get_access_date_as_epoch(header_filepath)
        new_folder = os.path.join(pathlib.Path(filepath).parent,
                                  f'{pathlib.Path(filepath).name}_{last_modified_epoch}a')

    try:
        os.mkdir(new_folder)
    except FileExistsError:
        pass

    shutil.move(filepath, os.path.join(new_folder, pathlib.Path(filepath).name))
    shutil.move(header_filepath, os.path.join(new_folder, pathlib.Path(header_filepath).name))

    print(f"Old file moved to {new_folder}")


def download_with_headers(url, path, index, total):
    wrote_file = False
    headers = {'user-agent': 'c384da2W9f73dz20403d'}

    local_filename = url.split('/')[-1]


    if local_filename == "COM3008.bin":
        local_filename = "COM3008a.bin"
        url = url.replace("COM3008.bin", "COM3008a.bin")
    elif local_filename == "ECOM3005a.bin":
        local_filename = "COM3005a.bin"
        url = url.replace("ECOM3005a.bin", "COM3005a.bin")

    target_path = os.path.join(path, local_filename)
    target_headers_path = os.path.join(path, f"{local_filename}_headers.txt")
    response_headers = None

    print(f"({index}/{total}): {local_filename}")

    retries = 3
    success = False
    for n in range(retries):
        time.sleep(randint(1, 5))
        with requests.get(url, stream=True, headers=headers) as r:
            response_headers = r.headers
            try:
                r.raise_for_status()
                success = True
            except HTTPError as exc:
                code = exc.response.status_code

                if code == 404:
                    print(f"[WARNING] Got 404 for {local_filename}")
                    break
                elif code != 200:
                    # retry after n seconds
                    print(f"[WARNING] Got {code} for {local_filename}, retrying after {n + 1} seconds")
                    time.sleep(n + 1)
                    continue


                raise

            if check_for_older_headers(response_headers, target_path, target_headers_path):
                try:
                    move_older_file(target_path, target_headers_path)
                except FileNotFoundError:
                    pass
                #if not os.path.exists(header_filepath):
                #    return False
                with open(target_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        # If you have chunk encoded response uncomment if
                        # and set chunk_size parameter to None.
                        # if chunk:
                        f.write(chunk)

                    wrote_file = True

                    stripped = [(key, x) for key, x in response_headers.items()]

                    with open(target_headers_path, newline="\r\n", mode="w") as of:
                        lines = [f"{name}: {value}\n" for name, value in stripped]
                        lines.append("\n")
                        of.writelines(lines)
            else:
                print("|--------> Exists, skipping...")
                break



    if not success:
        print(f"[WARNING] Skipping {local_filename} after reaching maximum retries")

    return response_headers, local_filename, wrote_file





def get_purchased(username, password):
    r = requests.post(
        'http://api.amusement-center.com/api/dcp/v1/getcontentslist',
        headers={'User-Agent': USER_AGENT},
        data={
            'userid': username,
            'passwd': password
        }
    )
    if not r.status_code == 200:
        raise ConnectionError("Could not get list of purchased content.")

    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f'server_response_{timestamp}.bin'
    with open(filename, 'w+b') as f:
        f.write(r.content)

    print(f"Wrote to {filename}")

    filename = f'response_headers_{timestamp}.txt'
    with open(filename, 'w') as f:
        f.write(str(r.headers))

    print(f"Wrote to {filename}")

    data = r.content
    data = data.decode("euc_jisx0213")

    first_comma_pos = data.find(',')
    if first_comma_pos == -1:
        status = data
        data = ""
    else:
        status = data[:first_comma_pos]
        data = data[first_comma_pos + 1:]
    if status != 'ok':
        raise ValueError("Could not get list of purchased content. Login credentials may have been incorrect.")

    return tuple(parse_content_entries(data))


def get_purchased_from_file():
    with open('server_response.bin', 'r', "euc_jisx0213") as f:
        data = f.read()

    first_comma_pos = data.find(',')
    if first_comma_pos == -1:
        status = data
        data = ""
    else:
        status = data[:first_comma_pos]
        data = data[first_comma_pos + 1:]
    if status != 'ok':
        raise ValueError("Could not get list of purchased content. Login credentials may have been incorrect.")

    return tuple(parse_content_entries(data))

def parse_content_entries(data):
    data = data.replace(',', '\n')
    data = StringIO(data)
    data.seek(0, SEEK_END)
    end = data.tell()
    data.seek(0)
    while data.tell() < end:
        yield parse_content_entry(data)

CONTENT_PROPERTIES = (
    # (key, transformer).
    ('egg',               str),
    ('version',           str),
    ('title',             str),
    ('productId',         str),
    ('publisher',         str),
    ('platform',          str),
    ('genre',             str),
    ('year',              str),
    ('mystery1',          str),
    ('gameFilename',      str),
    ('mystery2',          str), # Last file update date, YYYYMMDDhhmm
    ('mystery3',          str),
    ('owned',             lambda s: bool(int(s))),
    ('thumbnailFilename', str),
    ('description',       str),
    ('mystery5',          str),
    ('manualFilename',    str),
    ('manualDate',        str), # Only appears if the game has a manual...?
    ('musicFilename',     str), # Only appears if the game has music...?
    ('musicDate',         str),
    ('lastUpdate',        str),
    ('mystery6',          str), # Some future date...? An expiration?
    ('mystery7',          str), # A date - possibly the "added on" date?
    ('mystery8',          str), # Another future date; possibly always the same as mystery6.
    ('mystery9',          str),
    ('region',            int), # 0: Japanese; 1: English
    ('mystery10',         str)
)


def parse_content_entry(data):
    return {key: transformer(unquote_plus(data.readline().rstrip('\n'), encoding='euc_jisx0213'))
                for key, transformer in CONTENT_PROPERTIES}


def get_server_json(args):
    if USE_SERVER_RESPONSE_FILE:
        entries = get_purchased_from_file()
    else:
        if args.pw is None or args.user is None:
            print("Please enter your Project EGG...")

        if args.user is None:
            username = input("Username: ")
        else:
            username = args.user

        if args.pw is None:
            password = input("Password: ")
        else:
            password = args.pw

        entries = get_purchased(username, password)

    filename = f"data_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=4)

    print(f"Wrote to {filename}")

    return filename


def download(args):
    if args.server_json is not None:
        server_json = args.server_json
    else:
        server_json = get_server_json(args)

    if args.dest is not None:
        dest = args.dest
        os.makedirs(dest, exist_ok=True)
    else:
        dest = "."

    file_list = generate_file_list(server_json)
    download_results = [
        download_with_headers(f'http://www.amusement-center.com/productfiles/EGGFILES/{x}', dest,
                              idx, len(file_list)) for idx, x in enumerate(file_list, start=1)]
    # print(path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="deviled-eggs v1.0: Tools for retrieving, romanizing, and datting the Project EGG files "
                    "import",
        epilog="Copyright 2023-01-15 - Icyelut. GPLv3",
        fromfile_prefix_chars='@')

    parser.set_defaults(func_to_run=dat)

    subparsers = parser.add_subparsers(help="Subcommand help")

    download_parser = subparsers.add_parser("download", help="File download mode")
    download_parser.add_argument("--server_json", metavar="<server response JSON path>", type=is_file(True),
                                 help="Full path to the JSON response file with game metadata", required=False)
    download_parser.add_argument("--user", metavar="<username>",
                                 help="Your Project EGG user account username", required=False)
    download_parser.add_argument("--pw", metavar="<password>",
                                 help="Your Project EGG user account password", required=False)
    download_parser.add_argument("dest", metavar="<destination path>", type=pathlib.Path,
                                 help="Full path to the folder where the files should be saved")
    download_parser.set_defaults(func_to_run=download)

    romanize_parser = subparsers.add_parser("romanize", help="Romanization tools")
    romanize_parser.add_argument("server_json", metavar="<server response JSON path>", type=is_file(True),
                            help="Full path to the JSON response file with game metadata")
    romanize_parser.add_argument("--romanized_csv", metavar="<romanized titles CSV path>", type=is_file(True),
                            help="Full path to the existing CSV with romanized titles")
    romanize_parser.add_argument("out_dir", metavar="<output XML path>", type=is_valid_new_file_location,
                            help="Path to write the csv to")
    romanize_parser.set_defaults(func_to_run=romanize)

    dat_parser = subparsers.add_parser("dat", help="No-intro dat generator")
    dat_parser.add_argument("dumper",
                            help="Put your name!")

    dat_parser.add_argument("--hash_csv", metavar="<hash csv>", type=pathlib.Path,
                            help="Use a hashes_***.csv from a previous run to skip previously hashed files")

    dat_parser.add_argument("cdn_dir", metavar="<CDN files path>", type=pathlib.Path,
                            help="Full path to the folder with the actual .bin files as a flat directory (no subfolders)")

    dat_parser.add_argument("server_json", metavar="<server response JSON path>", type=is_file(True),
                            help="Full path to the JSON response file with game metadata")

    dat_parser.add_argument("romanized_csv", metavar="<romanized titles CSV path>", type=is_file(True),
                            help="Full path to the CSV with romanized titles")

    dat_parser.add_argument("out_dat", metavar="<output XML path>", type=is_valid_new_file_location,
                            help="Name of path to write output dats to")

    dat_parser.set_defaults(func_to_run=dat)

    parsed_args = parser.parse_args()

    if "func_to_run" in parsed_args:

        parsed_args.func_to_run(parsed_args)

    else:
        print("No function to run. Quitting.")
        parser.print_help()
        sys.exit(0)

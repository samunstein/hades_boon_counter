import dataclasses
import os
import re
from collections import defaultdict
from datetime import datetime
from io import BytesIO
from tkinter import Tk, Label, Frame, BOTH

from luabins import *
from lz4 import block

LIST_HAMMER = False


def read_file(filename):
    with open(filename, "rb") as fil:
        stream = BytesIO(fil.read())
    stream.seek(0)
    signature = stream.read(4).decode("UTF-8")
    checksum = stream.read(4)
    version = int.from_bytes(stream.read(4), "little")
    timestamp = int.from_bytes(stream.read(8), "little")
    location = luabins._read_string(stream)
    runs = luabins._read_int(stream)
    meta_points = luabins._read_int(stream)
    shrine_points = luabins._read_int(stream)
    godmode = luabins._read_short_short_int(stream)
    hellmode = luabins._read_short_short_int(stream)
    luakeys_len = luabins._read_int(stream)
    luakeys = []
    for _ in range(luakeys_len):
        luakeys.append(luabins._read_string(stream))
    current_map = luabins._read_string(stream)
    startingmap = luabins._read_string(stream)

    binlength = luabins._read_int(stream)
    compressed = BytesIO()

    for _ in range(binlength):
        compressed.write(luabins._read_short_short_int(stream).to_bytes(1))
    compressed.seek(0)

    decompressed = block.decompress(compressed.read(), binlength * 10)
    dec_bytes = BytesIO(decompressed)
    data = luabins.decode_luabins(dec_bytes)
    return data


@dataclasses.dataclass(frozen=True, repr=True)
class Trait:
    gods: list[str]
    name: str
    rarity: str


def read_god_keepsakes(data):
    blocked = data[0]["CurrentRun"]["BlockedKeepsakes"] if "BlockedKeepsakes" in data[0]["CurrentRun"] else dict()
    taken = []
    for b in blocked.values():
        match = re.match("Force([A-Za-z]+)BoonTrait", b)
        if match:
            taken.append(match.groups()[0])
    traitdict = data[0]["CurrentRun"]["Hero"]["TraitDictionary"]
    for t in traitdict:
        match = re.match("Force([A-Za-z]+)BoonTrait", t)
        if match:
            taken.append(match.groups()[0])
    return taken


def read_traits(data):
    traitdict = data[0]["CurrentRun"]["Hero"]["TraitDictionary"]
    trait_list = []
    for trait in traitdict.values():
        trait_d = trait[1]
        if "God" in trait_d:
            trait_list.append(Trait([trait_d["God"]], trait_d["Name"], trait_d["Rarity"]))
        elif LIST_HAMMER and "Frame" in trait_d and trait_d["Frame"] == "Hammer":
            trait_list.append(Trait(["Hammer"], trait_d["Name"], "Common"))
        elif "Frame" in trait_d and trait_d["Frame"] == "Duo":
            gods_re = re.match("([A-Za-z]+)_([A-Za-z]+)_[0-9]+", trait_d["Icon"])
            gods = gods_re.groups()
            trait_list.append(Trait(list(gods), trait_d["Name"], "Duo"))
        elif "Icon" in trait_d and "Chaos_Blessing" in trait_d["Icon"]:
            trait_list.append(Trait(["Chaos"], trait_d["Name"], trait_d["Rarity"]))
        elif "Icon" in trait_d and "Rarity" in trait_d:
            god_re = re.match("Boon_([A-Za-z]+)_[0-9]+", trait_d["Icon"])
            if god_re is not None:
                god = god_re.groups()
                trait_list.append(Trait(list(god), trait_d["Name"], trait_d["Rarity"]))
    return trait_list


def find_save_folder():
    home = os.path.expanduser("~")
    try:
        savefilesdir = f"{home}/Documents/Saved Games/Hades"
        os.listdir(savefilesdir)
    except FileNotFoundError as e:
        savefilesdir = input("Cannot find saved games. Pls tell directory: ")

    try:
        saves = os.listdir(savefilesdir)
    except FileNotFoundError as e:
        input("Invalid save files dir.")
        quit()
    return savefilesdir


def find_save_file(savefilesdir):
    saves = os.listdir(savefilesdir)
    relevant = [s for s in saves if re.match("^[A-Za-z0-9]+_Temp.sav$", s) is not None]
    with_times = [(r, os.path.getmtime(f"{savefilesdir}/{r}")) for r in relevant]
    if not with_times:
        return None, None
    file, time = list(sorted(with_times, key=lambda a: a[1], reverse=True))[0]

    return f"{savefilesdir}/{file}", time


def main():
    directory = find_save_folder()
    file, current_time = find_save_file(directory)
    if file is None:
        input("Save file with run data doesn't exist probably")
        quit()

    def update():
        nonlocal current_time

        file, time = find_save_file(directory)
        if file is None:
            root.after(2000, update)
            return

        if time == current_time:
            root.after(2000, update)
            return

        current_time = time

        filelabel.config(text=file)
        modifiedlabel.config(text=datetime.fromtimestamp(current_time).isoformat())

        filedata = read_file(file)

        keepsakes = read_god_keepsakes(filedata)
        traits = read_traits(filedata)

        god_tally = defaultdict(lambda: 0)
        for k in keepsakes:
            god_tally[k] = 0
        for trait in traits:
            for god in trait.gods:
                god_tally[god] += 1

        for w in boonframe.winfo_children():
            w.destroy()

        totalboons = 0
        totalkeepsakes = len(keepsakes)

        for god in sorted(god_tally):
            keepsake = " + keepsake" if god in keepsakes else ""
            l = Label(
                master=boonframe,
                text=f"{god}: {god_tally[god]} boon{"s" if god_tally[god] != 1 else ""}{keepsake}"
            )
            l.config(padx=15, pady=5, anchor="w", font=("Arial", 20))
            l.pack(fill=BOTH)

            if god != "Chaos":
                totalboons += god_tally[god]

        l = Label(
            master=boonframe,
            text=f"Total: {totalboons} nonchaos boon{"s" if totalboons != 1 else ""}, {totalkeepsakes} keepsake{"s" if totalkeepsakes != 1 else ""}"
        )
        l.config(padx=15, pady=15, anchor="w", font=("Arial", 22))
        l.pack(fill=BOTH)

        root.after(2000, update)
        return

    root = Tk()
    root.title = "Boon calculator"

    headframe = Frame()
    headframe.config(padx=10, pady=10)
    filelabel = Label(headframe, text="")
    filelabel.grid(row=0, column=0)
    modifiedlabel = Label(headframe, text="")
    modifiedlabel.grid(row=0, column=1)

    boonframe = Frame()
    boonframe.config(padx=10, pady=10)

    headframe.pack()
    boonframe.pack()

    # For first update
    current_time = 0

    root.after(100, update)

    root.mainloop()


if __name__ == "__main__":
    main()

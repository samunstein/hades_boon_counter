import dataclasses
import re
import os
from datetime import datetime

from collections import defaultdict
from tkinter.constants import RIGHT

from lz4 import block
from io import BytesIO
from tkinter import Tk, Label, Frame, BOTH, LEFT

from luabins import *

LIST_HAMMER = False

def read_file(filename):
    with open(filename, "rb") as f:
        signature = f.read(4).decode("UTF-8")
        checksum = f.read(4)
        version = int.from_bytes(f.read(4), "little")
        timestamp = int.from_bytes(f.read(8), "little")
        location = luabins._read_string(f)
        runs = luabins._read_int(f)
        meta_points = luabins._read_int(f)
        shrine_points = luabins._read_int(f)
        godmode = luabins._read_short_short_int(f)
        hellmode = luabins._read_short_short_int(f)
        luakeys_len = luabins._read_int(f)
        luakeys = []
        for _ in range(luakeys_len):
            luakeys.append(luabins._read_string(f))
        current_map = luabins._read_string(f)
        startingmap = luabins._read_string(f)

        binlength = luabins._read_int(f)
        compressed = BytesIO()

        for _ in range(binlength):
          compressed.write(luabins._read_short_short_int(f).to_bytes(1))
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
    blocked = data[0]["CurrentRun"]["BlockedKeepsakes"]
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

        traits = read_traits(filedata)
        god_tally = defaultdict(lambda: 0)
        for trait in traits:
            for god in trait.gods:
                god_tally[god] += 1

        keepsakes = read_god_keepsakes(filedata)

        for w in boonframe.winfo_children():
            w.destroy()

        for god in sorted(god_tally):
            keepsake = " + keepsake" if god in keepsakes else ""
            l = Label(master=boonframe, text=f"{god}: {god_tally[god]} boons{keepsake}")
            l.config(padx=15, pady=5, anchor="w", font=("Arial", 20))
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
    boonframe.config(padx = 10, pady = 10)

    headframe.pack()
    boonframe.pack()

    # For first update
    current_time = 0

    root.after(100, update)

    root.mainloop()

if __name__ == "__main__":
    main()

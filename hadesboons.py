import dataclasses
import os
import re
from collections import defaultdict
from datetime import datetime
from io import BytesIO
from tkinter import Tk, Label, Frame, BOTH
from idlelib.tooltip import Hovertip

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

@dataclasses.dataclass(repr=True)
class Booncount:
    god: str

    normal: int
    duo: int
    legendary: int

    boons: list[str]

    def to_str(self):
        n = [f"{self.normal}N"] if self.normal else []
        l = [f"{self.legendary}L"] if self.legendary else []
        d = [f"{self.duo}D"] if self.duo else []
        return "\n".join([" ".join(n + d + l)] + self.boons)

    def sum(self):
        return self.normal + self.duo + 2 * self.legendary

    def add(self, trait: Trait):
        short = ""
        if trait.rarity == "Legendary":
            self.legendary += 1
            short = "L"
        elif trait.rarity == "Duo":
            self.duo += 1
            short = "D"
        else:
            self.normal += 1
            short = "N"
        self.boons.append(trait.name + " - " + short)


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


def read_traits(data, lang):
    traitdict = data[0]["CurrentRun"]["Hero"]["TraitDictionary"]
    trait_list = []
    for trait in traitdict.values():
        trait_d = trait[1]
        name = lang[trait_d["Name"]] if trait_d["Name"] in lang else trait_d["Name"]
        if LIST_HAMMER and "Frame" in trait_d and trait_d["Frame"] == "Hammer":
            trait_list.append(Trait(["Hammer"], name, "Common"))
        elif "Frame" in trait_d and trait_d["Frame"] == "Duo":
            gods_re = re.match("([A-Za-z]+)_([A-Za-z]+)_[0-9]+", trait_d["Icon"])
            gods = gods_re.groups()
            trait_list.append(Trait(list(gods), name, "Duo"))
        elif "Icon" in trait_d and "Chaos_Blessing" in trait_d["Icon"]:
            all_d = list(trait.values())
            for trait_d in all_d:
                trait_list.append(Trait(["Chaos"], name, trait_d["Rarity"]))
        elif "Icon" in trait_d and "Rarity" in trait_d and re.match("Boon_([A-Za-z]+)_[0-9]+", trait_d["Icon"]):
            god_re = re.match("Boon_([A-Za-z]+)_[0-9]+", trait_d["Icon"])
            god = god_re.groups()
            trait_list.append(Trait(list(god), name, trait_d["Rarity"]))
        elif "God" in trait_d:
            trait_list.append(Trait([trait_d["God"]], name, trait_d["Rarity"] if "Rarity" in trait_d else "Common"))
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

    langdict = read_langfile()

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
        traits = read_traits(filedata, langdict)

        god_tally = {}

        for k in keepsakes:
            god_tally[k] = Booncount(k, 0, 0, 0, [])
        for trait in traits:
            for god in trait.gods:
                if god not in god_tally:
                    god_tally[god] = Booncount(god, 0, 0, 0, [])
                god_tally[god].add(trait)

        for w in boonframe.winfo_children():
            w.destroy()

        totalboons = 0
        totalkeepsakes = len(keepsakes)

        for god in sorted(god_tally):
            keepsake = " + keepsake" if god in keepsakes else ""
            l = Label(
                master=boonframe,
                text=f"{god}: {god_tally[god].sum()} boon{"s" if god_tally[god] != 1 else ""}{keepsake}"
            )
            l.config(padx=15, pady=5, anchor="w", font=("Arial", 20))
            l.pack(fill=BOTH)

            Hovertip(l, god_tally[god].to_str(), hover_delay=0)

            if god != "Chaos":
                totalboons += god_tally[god].sum()

        l = Label(
            master=boonframe,
            text=f"Total: {totalboons} nonchaos boon{"s" if totalboons != 1 else ""}, {totalkeepsakes} keepsake{"s" if totalkeepsakes != 1 else ""}"
        )
        l.config(padx=15, pady=15, anchor="w", font=("Arial", 22))
        l.pack(fill=BOTH)

        root.after(2000, update)
        return

    root = Tk()
    root.title("Booncalculator")

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

def read_langfile():
    words = {}

    programfiles = os.environ["ProgramFiles(x86)"] if "ProgramFiles(x86)" in os.environ else "C:/Program Files (x86)"
    maybe_file = f"{programfiles}/Steam/steamapps/common/Hades/Content/Game/Text/en/HelpText.en.sjson"

    path = ""
    if os.path.exists(maybe_file):
        path = maybe_file
    else:
        hadespath = input("Cannot find hades game files. Please paste hades game files 'Content' folder (usually under Steam - steamapps - common - Hades): ")
        path = f"{hadespath}/Game/Text/en/HelpText.en.sjson"

    if not os.path.exists(path):
        print("Cannot find language file")
        return words

    with open(path, "r", encoding="UTF-8") as f:
        t = f.read()
        # Absolute madness, but should work for what it is used
        sections = t.split("{")

        for section in sections:
            idtext = re.search("Id = \"([A-Za-z0-9_]+)\"", section)
            valtext = re.search("DisplayName = \"(.+)\"", section)
            if idtext and valtext:
                words[idtext.group(1)] = valtext.group(1)
    return words



if __name__ == "__main__":
    main()

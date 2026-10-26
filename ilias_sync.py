#!/usr/bin/env python3
"""Inoffizieller ILIAS-Sync fuer die Uni Mannheim (nur eigene Kurse). Siehe README.md."""
import argparse, getpass, hashlib, json, os, re, subprocess, sys
from pathlib import Path
from urllib.parse import urljoin

DEFAULTS = {
    "target_dir": "",                 # Pflicht: Zielordner
    "username": "",                   # Pflicht: Uni-ID
    "keychain_service": "ilias-unima",
    "mapping": {},                    # "kursname-teil (klein)" -> Unterordner, erster Treffer gewinnt
    "ilias_subdir": "ILIAS",          # Kurse landen in <Ordner>/<ilias_subdir>/<Kurs>/
    "unsorted_dir": "Unsortiert",     # Kurse ohne Mapping
    "skip": ["license information"],  # Kurse mit diesen Namensteilen werden ignoriert
    "own_groups": {},                 # optional: "kursname-teil" -> eigene Gruppennummer ("<n>. PG"-Ordner anderer Gruppen werden uebersprungen)
    "max_mb": 200,
    "video_ext": [".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"],  # werden nie geladen
}


def load_config(path):
    try:
        cfg = {**DEFAULTS, **json.loads(Path(path).read_text())}
    except FileNotFoundError:
        sys.exit(f"{path} fehlt: config.example.json nach config.json kopieren und anpassen.")
    if not (cfg["target_dir"] and cfg["username"]):
        sys.exit("config.json: target_dir und username muessen gesetzt sein.")
    return cfg


def has_copy(tmp, root):  # identical file (size, then sha256) already anywhere in the course folder?
    h = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    same = [p for p in root.rglob("*") if p != tmp and p.is_file() and p.stat().st_size == tmp.stat().st_size]
    return bool(same) and h(tmp) in map(h, same)


def get_password(cfg):  # Keychain -> ILIAS_PASSWORD -> Prompt
    r = subprocess.run(["security", "find-generic-password", "-s", cfg["keychain_service"],
                        "-a", cfg["username"], "-w"], capture_output=True, text=True)
    return (r.stdout.strip() if r.returncode == 0 else "") or os.environ.get("ILIAS_PASSWORD") \
        or getpass.getpass(f"ILIAS-Passwort fuer {cfg['username']}: ")


def clean(name):
    return re.sub(r'[/\\:\0]', "-", name).strip(" .") or "_"


def size_bytes(txt):  # "4.47 MB" / "1,2 GB" -> Bytes, None wenn keine Groesse
    m = re.fullmatch(r"([\d.,]+)\s*(B|KB|MB|GB)", txt.strip())
    return m and float(m[1].replace(",", ".")) * 1024 ** "B KB MB GB".split().index(m[2])


def main():
    ap = argparse.ArgumentParser(description="Laedt Dateien deiner ILIAS-Kurse (Uni Mannheim) in einen lokalen Ordner.")
    ap.add_argument("-c", "--config", default=Path(__file__).parent / "config.json", help="Pfad zur config.json")
    cfg = load_config(ap.parse_args().config)

    from bs4 import BeautifulSoup
    from IliasDownloaderUniMA import IliasDownloaderUniMA

    root = Path(cfg["target_dir"]).expanduser()
    max_bytes = cfg["max_mb"] * 1024 * 1024
    video_ext = tuple(cfg["video_ext"])

    def target(course):  # <Ordner>/<ilias_subdir>/<Kurs> oder <unsorted_dir>/<Kurs>
        for key, folder in cfg["mapping"].items():
            if key.lower() in course.lower():
                return f"{folder}/{cfg['ilias_subdir']}/{clean(course)}"
        return f"{cfg['unsorted_dir']}/{clean(course)}"

    def other_group(name, context):  # "<n>. PG" mit n != eigene Gruppe?
        pg = re.search(r"(?:^|[\s[])(\d+)\.\s*PG\b", name)
        mine = next((n for k, n in cfg["own_groups"].items() if k.lower() in context.lower()), None)
        return bool(pg and mine and int(pg[1]) != mine)

    class Sync(IliasDownloaderUniMA):
        def login(self, login_id, login_pw):
            # ILIAS moved from CAS to SAML (Shibboleth IdP idp.uni-mannheim.de); package 0.5.0 still posts to CAS.
            from requests import session
            from bs4 import BeautifulSoup
            from urllib.parse import urljoin
            self.session = s = session()
            r = s.get(urljoin(self.base_url, "login.php"))  # -> saml.php -> idp ... SSO?execution=e1s1
            soup = BeautifulSoup(r.content, "lxml")
            form = soup.find("form", id="login-form")
            if not form:
                raise ConnectionError(f"Unexpected ILIAS login page (no IdP login form) at {r.url}")
            data = {i["name"]: i.get("value", "") for i in form.select("input[type=hidden]")}
            data.update(j_username=login_id, j_password=login_pw, _eventId_proceed="")
            r = s.post(urljoin(r.url, form["action"]), data=data)
            for _ in range(3):  # IdP may show an attribute-consent page before the SAMLResponse auto-post form
                soup = BeautifulSoup(r.content, "lxml")
                if soup.find("input", {"name": "SAMLResponse"}):
                    form = soup.find("input", {"name": "SAMLResponse"}).find_parent("form")
                    r = s.post(urljoin(r.url, form["action"]),
                               data={i["name"]: i.get("value", "") for i in form.select("input[name]")})
                    break
                if soup.select_one(".output--error") or soup.find("input", {"name": "j_password"}):
                    err = soup.select_one(".output--error")
                    raise ConnectionError("ILIAS login failed: wrong uni-id or password"
                                          + (f" (IdP: {err.get_text(' ', strip=True)})" if err else ""))
                form = soup.find("form")
                if not (form and form.find(attrs={"name": "_eventId_proceed"})) \
                        or form.select("input[type=text], input[type=number], input[type=password], input[type=tel]"):
                    raise ConnectionError(f"Unexpected IdP page after login (MFA?) at {r.url}")
                data = {i["name"]: i.get("value", "") for i in form.select("input[name]") if i.get("type") != "checkbox"}
                r = s.post(urljoin(r.url, form["action"]), data={**data, "_eventId_proceed": ""})
            else:
                raise ConnectionError(f"Unexpected IdP page after login at {r.url}")
            r = s.get(self.base_url)
            if "ilias.uni-mannheim.de" not in r.url or "logout" not in r.text.lower():
                raise ConnectionError(f"SAML login went through but ILIAS shows no session (landed on {r.url})")
            self.login_soup = BeautifulSoup(r.content, "lxml")

        # ILIAS 9 UI: package 0.5.0 scrapes ILIAS 5 HTML and finds nothing, so courses/files are walked here.
        def my_courses(self):
            r = self.session.get(urljoin(self.base_url, "ilias.php?baseClass=ilDashboardGUI&cmd=jumpToMemberships"))
            found = {}
            for a in BeautifulSoup(r.content, "lxml").select(".il-item-title a[href]"):
                if re.search(r"goto\.php/crs/\d+", a["href"]):
                    found[a["href"]] = a.get_text(strip=True)
            return [(n, u) for u, n in found.items()
                    if not any(k.lower() in n.lower() for k in cfg['skip'])]

        def walk(self, url, dest, seen):
            soup = BeautifulSoup(self.session.get(url).content, "lxml")
            for it in soup.select(".ilContainerListItemOuter"):
                a = it.select_one("a.il_ContainerItemTitle[href]")
                if not a or a["href"] in seen:
                    continue
                seen.add(a["href"])
                title, href = clean(a.get_text(strip=True)), urljoin(url, a["href"])
                if re.search(r"goto\.php/fold/\d+", href):
                    if other_group(title, str(dest)):
                        continue
                    self.walk(href, dest / title, seen)
                elif "cmd=sendfile" in href or "goto.php/file/" in href:
                    props = [p.get_text(" ", strip=True) for p in it.select(".il_ItemProperty")]
                    ext = props[0].lower() if props and re.fullmatch(r"\w{1,6}", props[0]) else ""
                    name = title if not ext or title.lower().endswith("." + ext) else f"{title}.{ext}"
                    if name.lower().endswith(video_ext) or "." + ext in video_ext:
                        print(f"[skip video] {(dest / name).relative_to(root)}")
                        continue
                    self.download(href, dest / name, next(filter(None, map(size_bytes, props)), 0))

        def download(self, href, path, size):
            if path.exists():  # never overwrite
                return
            if size > max_bytes:
                return print(f"[skip >max_mb] {path.relative_to(root)} ({size / 1e6:.0f} MB)")
            with self.session.get(href, stream=True) as r:
                r.raise_for_status()
                if int(r.headers.get("content-length") or 0) > max_bytes:
                    return print(f"[skip >max_mb] {path.relative_to(root)}")
                if r.headers.get("content-type", "").startswith("video/"):  # title/ext gave no hint
                    return print(f"[skip video] {path.relative_to(root)}")
                if "text/html" in r.headers.get("content-type", ""):
                    return print(f"[skip, no file] {path.relative_to(root)}")
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_name(path.name + ".part")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 16):
                        f.write(chunk)
                rel = path.relative_to(root).parts  # course folder: <Ordner>/<ilias_subdir>/... or <unsorted_dir>/<Kurs>/...
                if has_copy(tmp, root.joinpath(*rel[:1 if rel[1] == cfg["ilias_subdir"] else 2])):
                    tmp.unlink()
                    try: path.parent.rmdir()
                    except OSError: pass
                    return print(f"[skip, already in course folder] {path.relative_to(root)}")
                tmp.rename(path)
            self.downloaded += 1
            print(f"[file] {path.relative_to(root)}")

    m = Sync()
    m.login(cfg["username"], get_password(cfg))
    m.downloaded = 0
    for course, url in m.my_courses():
        print(f"[map] {course} -> {target(course)}")
        m.walk(url, root / target(course), set())
    print(f"[done] {m.downloaded} new file(s)")


if __name__ == "__main__":
    main()

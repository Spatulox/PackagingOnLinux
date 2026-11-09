# Plan : CompileOnLinux, outil de packaging multi-formats Linux + Windows (Python + CI)

## Avancement

- [x] 1. Socle : config, staging, core, CLI, backend tar.gz, tests
- [x] 2. deb + rpm (sans sudo, détection des dépendances)
- [x] 3. Interface graphique Qt (PySide6 ou PyQt6)
- [ ] 4. CI GitHub / GitLab
- [ ] 5. AppImage, puis Flatpak, puis Snap
- [ ] 6. Construction en conteneur (`--container`)
- [ ] 7. Dogfooding : CompileOnLinux se package lui-même
- [ ] 8. Nettoyage : suppression de `scripts/` et `purge_build_install_myges.sh`, mise à jour du README
- [ ] 9. Langue de l'interface : anglais et français, au choix dans les paramètres
- [ ] 10. Windows : installeur `.exe` (NSIS) et archive portable `.zip`, construits depuis Linux

## Contexte

Au départ, le repo contenait deux scripts bash (`scripts/deb.sh`, `scripts/rpm.sh`) codés en dur pour `MyGesClient`. Ils demandaient `sudo`, appelaient `sudo` dans le `postinst`, et posaient l'icône à un chemin non standard (`/usr/share/icons/<nom>/`). L'objectif : une seule interface où l'utilisateur décrit son logiciel une fois, choisit les formats (deb, rpm, AppImage, Flatpak, Snap…), et obtient les paquets. Ça doit tourner sur n'importe quelle distro et n'importe quel environnement de bureau, et surtout en CI GitHub/GitLab.

**Périmètre** : l'entrée est un logiciel **déjà compilé** (un binaire ou un dossier d'install). Une commande `build` optionnelle dans la config permet de compiler les sources juste avant, mais l'outil ne gère pas lui-même les chaînes de compilation propres à chaque langage.

## Choix techniques

- **Python ≥ 3.11, zéro dépendance pour le cœur** : `tomllib` pour la config, `argparse`, `subprocess`, `shutil`. On l'installe avec `pipx install .`, ou on le lance sans installation via `python3 -m compileonlinux`.
- **Interface graphique Qt (PySide6 ou PyQt6)** : c'est la porte d'entrée principale. Elle rend simple l'ajout d'un logiciel : on choisit le binaire, l'icône, on remplit nom/version/description, on coche les formats, puis on clique sur « Construire ». Qt s'affiche correctement sur GNOME, KDE, XFCE, etc., sous X11 comme sous Wayland. Elle tourne avec PySide6 (dépendance optionnelle `pip install .[gui]`) ou PyQt6 (paquet `python3-pyqt6` des distributions), pour que la CLI et la CI restent sans dépendance.
- **Config déclarative `packaging.toml`**, que la GUI lit et écrit. C'est le format d'échange entre la GUI, la CLI et la CI : on configure un projet visuellement, on committe le `packaging.toml`, et la CI produit les mêmes paquets.
- **Indépendant du bureau** : uniquement des standards freedesktop. Le `.desktop` est validé avec `desktop-file-validate`, l'icône va dans le thème `hicolor` (`usr/share/icons/hicolor/<taille>/apps/<id>.png`), et un AppStream `metainfo.xml` est généré (requis par Flatpak, utile pour GNOME Logiciels comme pour KDE Discover). Aucun `sudo` ni `gtk-update-icon-cache` en dur dans les scripts de mainteneur : deb et rpm ont déjà des triggers système pour ça.
- **Pas de root pour construire** : `dpkg-deb --root-owner-group` remplace les `sudo chown`, et `rpmbuild` utilise un `--define "_topdir <tmp>"` au lieu de `~/rpmbuild`.
- **Portabilité de l'hôte** : chaque backend déclare les outils dont il a besoin, et la commande `doctor` dit ce qui manque. Avec l'option `--container` (docker/podman), chaque format sera construit dans l'image officielle adaptée (debian, fedora, ubuntu+snapcraft, flatpak-builder). On pourra donc produire un `.rpm` depuis Debian, etc.

## Architecture

```
compileonlinux/
  __main__.py, cli.py        # sous-commandes: init, doctor, check, build, gui
  config.py                  # lecture + validation de packaging.toml -> AppSpec (dataclass)
  elf.py                     # détection de l'architecture depuis l'en-tête ELF
  staging.py                 # arbre FHS commun (usr/bin, .desktop, icônes hicolor, metainfo)
  deps.py                    # détection des dépendances (reprend scripts/list_dep.py)
  runner.py                  # exécution des commandes avec journal en direct
  core.py                    # API commune build(spec, formats, log) utilisée par la CLI ET la GUI
  backends/
    base.py                  # interface: required_tools, build(ctx) -> list[Path]
    deb.py  rpm.py  tarball.py
    appimage.py  flatpak.py  snap.py      # à venir
  gui/
    app.py                   # QMainWindow, point d'entrée `compileonlinux-gui`
    form.py                  # formulaire AppSpec (champs, sélecteurs de fichiers, aperçu de l'icône)
    formats.py               # cases à cocher des formats + état « outil dispo/manquant » (issu de doctor)
    worker.py                # QThread qui lance core.build et diffuse les logs en direct
ci/                                       # à venir
  github/action.yml          # action composite réutilisable
  github/example-workflow.yml
  gitlab/compileonlinux.gitlab-ci.yml   # template à inclure avec `include:`
examples/mygesclient/packaging.toml
tests/                       # pytest + pytest-qt, app fixture "hello" (script shell + icône)
```

Principes clés :
- **Un seul staging FHS**, que chaque backend réutilise. On écrit donc une seule fois la logique « où va quel fichier ».
- **La GUI ne contient aucune logique de packaging** : elle remplit un `AppSpec` et appelle `core.build`. La CLI et la CI font exactement la même chose.
- **Un format qui échoue n'arrête pas les autres** : l'erreur est rapportée dans le résultat.
- Un nouveau backend ajouté à `BACKENDS` apparaît automatiquement dans la CLI et dans la GUI.

Écran principal de la GUI (une seule fenêtre) :
```
┌ CompileOnLinux ─────────────────────────────────────────┐
│ [Nouveau] [Ouvrir] [Enregistrer] [Enregistrer sous]      │
│ Application : Nom / ID / Version / Résumé / Description  │
│               Mainteneur / Licence / Site web / Catégorie│
│ Fichiers : Binaire [..........] [Parcourir]  Arch: amd64 │
│            Icône   [..........] [Parcourir]  [aperçu]    │
│            Commande de compilation (optionnelle)         │
│ Dépendances : ☑ auto   En plus (deb) / En plus (rpm)     │
│ Formats : ☑ deb ☑ rpm ☑ tar.gz ☐ AppImage ⚠ ...          │
│           (⚠ = outil manquant, survol → commande d'install)│
│ Dossier de sortie: [builds/]                              │
│ [ Construire les paquets ]   [Ouvrir le dossier de sortie]│
│ ┌ Journal ───────────────────────────────────────────┐   │
│ │ [deb] OK builds/mygesclient_1.0.0_amd64.deb         │   │
│ └────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

Exemple de `packaging.toml` :
```toml
[app]
id = "io.github.spatulox.MyGesClient"   # reverse-DNS, requis par Flatpak
name = "MyGesClient"
version = "1.0.0"
summary = "MyGes native desktop client"
license = "GPL-3.0-only"
maintainer = "Spatulox"
categories = ["Education"]

[files]
binary = "MyGesClient"           # ou `dir = "dist/"` + `exec = "bin/app"` pour une app multi-fichiers
icon = "icons/appicon.png"

[build]                          # optionnel, reçoit $APP_VERSION, $APP_NAME, $APP_ID
command = "wails build"

[deps]                           # optionnel, sinon auto-détection
auto = true
deb = ["libgtk-3-0"]
rpm = ["gtk3"]

[output]
formats = ["deb", "rpm", "tarball"]
dir = "builds"
```

## Détail par backend

| Format | Outil | Remarques | État |
|---|---|---|---|
| deb | `dpkg-deb --root-owner-group` | `Depends` via `dpkg-shlibdeps`, sinon ldd + `dpkg -S` ; vérification avec `lintian` | fait |
| rpm | `rpmbuild -bb`, topdir temporaire | les dépendances `.so` sont détectées automatiquement par rpm (AutoReq) ; vérification avec `rpmlint` | fait |
| tar.gz | Python `tarfile` | solution de repli universelle | fait |
| AppImage | `appimagetool` (téléchargé dans un cache, à version fixe) | AppDir généré depuis le staging. Les libs GTK/WebKit ne sont pas embarquées par défaut (option `linuxdeploy` plus tard) | à faire |
| Flatpak | `flatpak-builder` + `flatpak build-bundle` | manifest généré, sortie `.flatpak`. En CI : conteneur `ghcr.io/flathub-infra/flatpak-github-actions`. Nécessite une icône carrée | à faire |
| Snap | `snapcraft --destructive-mode` dans un conteneur Ubuntu | confinement `strict` + extension `gnome` si GTK, sinon `classic` | à faire |

L'architecture est détectée automatiquement à partir de l'en-tête ELF (amd64/x86_64, arm64/aarch64, etc.) ; un script est marqué `all`/`noarch`.

## Étapes de réalisation

1. **Socle** : `config.py`, `staging.py`, `core.py`, `cli.py` (`init`, `doctor`, `check`, `build`), backend `tarball`, tests pytest.
2. **deb + rpm** : port de `scripts/deb.sh` et `scripts/rpm.sh` en Python sans sudo, logique de `list_dep.py` reprise dans `deps.py`. `examples/mygesclient/packaging.toml` sert de référence.
3. **GUI Qt** : formulaire, ouverture et enregistrement du `packaging.toml`, cases des formats reliées à `doctor`, build dans un `QThread` avec logs en direct, bouton « Ouvrir le dossier de sortie ».
4. **CI** : action GitHub composite et template GitLab. Un job par format (matrice), chacun dans son image dédiée ; les paquets sont publiés comme artefacts, et attachés à la release quand un tag est poussé.
5. **AppImage**, puis **Flatpak**, puis **Snap** (du plus simple au plus contraignant en CI). Chaque nouveau backend apparaît automatiquement dans la GUI.
6. **Option `--container`** (case à cocher dans la GUI) pour construire tous les formats localement depuis n'importe quelle distro.
7. **Dogfooding** : CompileOnLinux se package lui-même (AppImage et Flatpak de la GUI) via son propre `packaging.toml` et sa propre CI.
8. **Nettoyage** : suppression de `scripts/` et `purge_build_install_myges.sh`, mise à jour du README et de `CLAUDE.md`.
9. **Langue de l'interface (EN / FR)** : voir la section dédiée plus bas.
10. **Windows (.exe)** : voir la section dédiée plus bas.

## Langue de l'interface (EN / FR)

- **Module `compileonlinux/i18n.py`** : un dictionnaire de traductions par langue (`en`, `fr`) et une fonction `tr("clé")`. Ajouter une langue revient à ajouter un dictionnaire, sans outil externe. Les fichiers `.ts`/`.qm` de Qt ne sont pas utilisés, car ils demandent `lupdate`/`lrelease` au moment de la construction.
- **Tous les textes de la GUI passent par `tr()`** : libellés, infobulles, messages d'erreur et boîtes de dialogue. Les textes déjà écrits en dur en français dans `gui/` sont migrés.
- **Menu « Paramètres → Langue / Language »** : le choix est enregistré avec `QSettings` (`~/.config/CompileOnLinux/`) et appliqué tout de suite, en reconstruisant les libellés sans redémarrer.
- **Langue par défaut** : celle du système (`QLocale.system()`). L'anglais est utilisé pour toute langue non traduite.
- **La CLI reste en anglais**, car sa sortie est destinée à la CI et aux journaux. Les messages d'erreur du cœur (validation de la config) passent aussi par `tr()`, pour s'afficher dans la langue choisie dans la GUI.
- **Tests** : chaque clé existe dans toutes les langues (test automatique), et le changement de langue met à jour les libellés (pytest-qt).

## Windows (.exe)

CompileOnLinux package des binaires **déjà compilés**. Un binaire Linux ne tourne pas sous Windows : il faut donc un binaire Windows en entrée. Beaucoup d'outils savent le produire depuis Linux, par exemple `wails build -platform windows/amd64`, `GOOS=windows go build`, `cargo build --target x86_64-pc-windows-gnu` ou PyInstaller sous Wine. Cette compilation se fait via la commande `[build]` existante, et l'outil ne gère pas lui-même les compilateurs.

- **Config** : nouvelle section optionnelle, indépendante des fichiers Linux :
  ```toml
  [windows]
  binary = "build/bin/MyGesClient.exe"     # ou dir = "dist-win/" + exec = "app.exe"
  icon = "build/windows/icon.ico"          # optionnel ; sinon converti depuis l'icône PNG
  build_command = "wails build -platform windows/amd64"   # optionnel
  ```
- **Backend `exe`** : génère un script NSIS, compilé par `makensis`, qui est disponible sous Linux (`apt install nsis`, `dnf install mingw32-nsis`) et donc en CI Linux. Le résultat est `<nom>-<version>-setup.exe`, avec :
  - installation dans `Program Files`, raccourcis dans le menu Démarrer et sur le bureau (optionnel) ;
  - désinstalleur, et entrée dans « Ajouter ou supprimer des programmes » (nom, version, éditeur, site web, icône) ;
  - architecture détectée depuis l'en-tête PE (x86, x64, arm64), comme `elf.py` le fait pour Linux.
- **Backend `zip`** : version portable sans installation (l'exécutable et ses fichiers dans un `.zip`), via le module Python `zipfile`. Aucun outil requis.
- **Signature de code (optionnelle, plus tard)** : `osslsigncode` avec un certificat fourni par variable d'environnement en CI. Sans signature, Windows SmartScreen affiche un avertissement au premier lancement : à documenter.
- **GUI** : un onglet ou un groupe « Windows » (binaire .exe, icône), affiché seulement quand un format Windows est coché.
- **Vérification** : tests unitaires sur le script NSIS généré et la détection PE. En CI, on construit l'installeur de l'app `hello`, puis on l'installe en mode silencieux (`setup.exe /S`) sur un runner `windows-latest` et on vérifie que l'exécutable et le désinstalleur sont présents.
- **Hors périmètre** : MSI (WiX ne fonctionne que sous Windows) et MSIX/Microsoft Store.

## Vérification

- `pytest` : parsing de la config, arbre de staging attendu, rendu des templates, détection d'architecture ELF.
- GUI : tests `pytest-qt` (le formulaire remplit bien un `AppSpec`, l'enregistrement puis la réouverture du TOML ne perdent rien, les cases des formats sont désactivées quand un outil manque), exécutés avec `QT_QPA_PLATFORM=offscreen`. Test manuel sur GNOME et KDE (X11 et Wayland).
- Intégration (job CI dédié) : on package l'app fixture `hello` dans tous les formats, puis on teste l'installation dans un conteneur propre :
  - `apt install ./*.deb` dans `debian:stable` et `ubuntu:latest`, puis `lintian` ;
  - `dnf install ./*.rpm` dans `fedora:latest`, puis `rpmlint` ;
  - `./*.AppImage --appimage-extract-and-run --version` ;
  - `flatpak install --user --bundle *.flatpak` puis `flatpak run` ;
  - `snap install --dangerous *.snap` (runner Ubuntu GitHub) ;
  - dans tous les cas : `desktop-file-validate` et `appstreamcli validate` sur les fichiers générés.
- Non-régression MyGesClient : `python3 -m compileonlinux build -c examples/mygesclient/packaging.toml --format deb`, puis installation et lancement.

## Points connus

- **MyGesClient et Fedora récent** : le binaire dépend de WebKitGTK 4.0, que Fedora ne fournit plus. Le `.rpm` se construit mais ne s'installe pas ; recompiler avec Wails `-tags webkit2_41` règle le problème.
- **Icône MyGesClient (521×536)** : non carrée, elle est installée dans `/usr/share/pixmaps` avec un avertissement. Il faudra une icône carrée (ex. 512×512) pour Flatpak et Snap.
- **Détection des dépendances deb** : ne fonctionne que si les bibliothèques de l'appli sont installées sur la machine qui construit ; sinon, les lister dans `[deps] deb`.

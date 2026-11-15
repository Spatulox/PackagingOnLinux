# Rapport : ajouter un serveur MCP à CompileOnLinux

## 1. Ce que le MCP apporterait

Un serveur MCP permettrait à un agent IA (Claude Code, Claude Desktop, un IDE…) de packager une application en conversation, par exemple « package mon binaire en deb et rpm ». L'agent lirait ou écrirait le `packaging.toml`, vérifierait la config, lancerait le build et lirait le résultat de chaque format.

Ce serait une **4ᵉ interface**, à côté de la CLI, de la GUI et de la CI. L'architecture s'y prête bien :

- **`core.build()` est déjà le seul point d'entrée pour construire.** Il prend un callback `log` et renvoie un `BuildResult` structuré (`packages`, `errors`, `warnings`), ce qui se transforme directement en réponse d'outil MCP.
- **`config.from_dict()` et `config.save()` existent déjà.** Le `packaging.toml` reste le format d'échange.
- **Les backends ajoutés à `BACKENDS` apparaîtront automatiquement dans le MCP**, comme pour la CLI et la GUI. AppImage, Flatpak et Snap n'exigeront donc aucun travail côté MCP.

## 2. Où le placer

```
compileonlinux/
  mcp/
    __init__.py
    server.py      # FastMCP : déclaration des outils et ressources, aucune logique de packaging
```

- **Point d'entrée :** une sous-commande `compileonlinux mcp` dans `cli.py`, avec un import protégé comme `cmd_gui` : un message clair si la lib manque. On peut aussi ajouter un script `compileonlinux-mcp` dans `[project.scripts]`.
- **Dépendance :** un extra optionnel `mcp = ["mcp>=1.2"]` dans `pyproject.toml` (le SDK Python officiel, avec `FastMCP`). Le cœur reste sans dépendance, comme pour la GUI. Comme pour Qt, `mcp` ne serait importé que dans `compileonlinux/mcp/`.
- **Transport :** `stdio`. C'est l'usage local standard, et c'est ce qu'attend `claude mcp add`.

Je ne recommande pas d'écrire soi-même le protocole JSON-RPC pour garder « zéro dépendance ». Ça ferait environ 200 lignes à maintenir pendant que le protocole évolue, pour un gain faible puisque le MCP est un usage de développeur, comme la GUI.

## 3. Outils à exposer

| Outil | Ce qu'il appelle | Ce qu'il renvoie | Annotation |
|---|---|---|---|
| `doctor` | `core.doctor()` | liste `{name, label, ok, missing, install_hint}` | lecture seule |
| `read_config(path)` | `config.load()` | le spec sous forme de dict (sections `app/files/build/deps/output`) | lecture seule |
| `check_config(path)` | logique de `cmd_check` (voir §4) | `problems`, `warnings`, résultat de `desktop-file-validate` et `appstreamcli` | lecture seule |
| `write_config(path, data, overwrite=false)` | `config.from_dict()`, `validate(check_files=False)`, `config.save()` | chemin écrit et problèmes éventuels | écriture |
| `suggest_id(name, maintainer)` | `config.suggest_id()` | une chaîne | lecture seule |
| `build(path, formats?, output_dir?)` | `core.build(spec, formats, log=...)` | `packages`, `errors`, `warnings` et la fin du journal | écriture, longue durée |

**Ressources** (données statiques que l'agent lit sans appeler d'outil) :
- `compileonlinux://schema` : la docstring de schéma de `config.py` et l'exemple de `PLAN.md`.
- `compileonlinux://formats` : les clés de `BACKENDS`, avec `label` et `required_tools`.
- `compileonlinux://categories` et `compileonlinux://licenses` : `MAIN_CATEGORIES` et `COMMON_LICENSES`.

**Prompt (optionnel) :** `package-app`, un guide pas à pas (`doctor`, puis `write_config`, `check_config` et `build`).

## 4. Refactorisations à faire avant

1. **Sortir la logique de `cmd_check` de `cli.py` vers `core.check(spec) -> CheckResult`** (dataclass avec `problems`, `warnings` et `validators: list[(tool, ok, output)]`). Aujourd'hui elle ne fait que `print()`, donc le MCP ne peut pas la réutiliser. La CLI se contenterait ensuite d'afficher le `CheckResult`, et la GUI pourrait l'utiliser aussi. Ça respecte la règle « aucune logique hors de `core` ».
2. **Ajouter `config.to_dict(spec, base_dir)`**, que `to_toml()` utiliserait en interne. Aujourd'hui `to_toml` construit ses sections en ligne. `read_config` renverrait ce dict, et l'aller-retour avec `from_dict()` serait symétrique et testable.

## 5. Points d'attention techniques

- **stdout est le canal du protocole en stdio.** Toute écriture parasite sur stdout casse la session. État actuel du code :
  - `core.build` utilise `print` comme `log` par défaut, donc le serveur doit toujours passer son propre callback.
  - Les sous-processus ne posent pas de problème : `runner.run` redirige vers `PIPE`, et `deps.py` utilise `capture_output=True`.
  - Par sécurité, envelopper chaque appel d'outil dans `contextlib.redirect_stdout(sys.stderr)`.
- **Les builds sont longs et bloquants** (`dpkg-shlibdeps`, `rpmbuild`, la commande `[build]` éventuelle) :
  - Déclarer l'outil `async` et lancer `core.build` dans un thread (`anyio.to_thread.run_sync`) pour ne pas bloquer la boucle d'événements.
  - Relayer les lignes `== <format>` comme notifications de progression (`ctx.report_progress` / `ctx.info`), pour que le client ne croie pas à un blocage.
  - Accumuler le journal dans une liste et n'en renvoyer que les N dernières lignes (le journal complet peut aussi aller dans un fichier de `output_dir`).
  - Les clients ont un timeout par outil (dans Claude Code, réglable avec `MCP_TOOL_TIMEOUT`) : à documenter.
- **Erreurs :**
  - `ConfigError` et `CommandError` (de la commande `[build]`) sont levées : les convertir en erreur d'outil avec le message.
  - Un format qui échoue n'est pas une erreur d'outil : il apparaît dans `errors` du résultat, ce qui reste cohérent avec `BuildResult`.
- **Sécurité, le point le plus important.** `[build] command` est exécutée avec `shell=True`. Un agent qui appelle `write_config` avec une commande de build puis `build` obtient donc l'exécution de commandes arbitraires. Recommandations :
  - `write_config` refuse de créer ou modifier `build.command` sauf avec un paramètre explicite `allow_build_command=true`. Ainsi l'utilisateur voit la commande dans la demande d'autorisation du client.
  - Mettre les annotations `destructiveHint` et `readOnlyHint` correctes sur chaque outil, pour que les clients demandent confirmation pour `build` et `write_config`.
  - Résoudre les chemins et les limiter au répertoire courant ou aux `roots` MCP du client.
  - Pas d'écrasement sans `overwrite=true`.
- **Distribution :** l'extra pip fonctionne tout de suite. En revanche, les paquets deb/rpm auto-construits ne dépendent que de `python3-pyqt6`. Le SDK `mcp` est peu ou pas empaqueté par les distributions, donc dans un premier temps le MCP serait disponible via `pip`/`pipx` seulement, et la sous-commande afficherait l'instruction d'installation si la lib manque. Le lanceur `packaging/compileonlinux` transmet déjà les arguments à la CLI, donc `compileonlinux mcp` fonctionnerait tel quel dès que la lib est présente.

## 6. Utilisation côté client

```bash
pipx install 'compileonlinux[mcp]'
claude mcp add compileonlinux -- compileonlinux mcp
```

ou un fichier `.mcp.json` à la racine d'un projet à packager :

```json
{ "mcpServers": { "compileonlinux": { "command": "compileonlinux", "args": ["mcp"] } } }
```

## 7. Tests

- Tester les fonctions des outils directement (ce sont des fonctions Python ordinaires) avec la fixture `hello_project` de `tests/conftest.py` : `write_config` puis `read_config` (aller-retour), `check_config`, et `build` en `tarball` (aucun outil externe requis).
- Un test de bout en bout avec la session client/serveur en mémoire du SDK (`mcp.shared.memory`) : lister les outils, appeler `doctor`, et vérifier que rien ne s'écrit sur stdout.
- Utiliser `pytest.importorskip("mcp")` pour que la suite passe sans l'extra.

## 8. Découpage en commits (une fonctionnalité par commit, selon `CLAUDE.md`)

1. `core.check()` et `CheckResult`, la CLI s'en sert (avec ses tests).
2. `config.to_dict()`, utilisé par `to_toml()` (avec ses tests).
3. Le serveur MCP : `compileonlinux/mcp/`, la sous-commande `mcp`, l'extra `[mcp]`, les tests, et la mise à jour de `README`, `CLAUDE.md` et `PLAN.md` (une nouvelle étape « Serveur MCP » dans l'avancement).

**Ordre conseillé :** après l'étape 4 (CI) ou en parallèle, car le MCP ne dépend d'aucune étape restante et profitera automatiquement des futurs backends et de `--container`. Quand `--container` existera, l'outil `build` devra simplement prendre un paramètre `container: bool` en plus.

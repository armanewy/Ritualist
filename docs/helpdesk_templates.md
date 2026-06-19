# Helpdesk Template Notes

The bundled helpdesk/runbook templates live in `setpiece\sample_recipes`:

- `support_triage_workspace.yaml`
- `meeting_audio_troubleshooting.yaml`
- `vendor_app_configuration_placeholder.yaml`
- `collect_basic_diagnostics.yaml`
- `lab_classroom_setup.yaml`
- `browser_admin_console_workspace.yaml`

They are samples for local editing and review. `setpiece init` does not install them, and no imported or shared recipe runs automatically.

Safety contract:

- Templates use variables for app commands, local paths, and URLs.
- Templates use structured actions only: browser opens, app launches, read-only assertions, and user confirmations.
- Templates do not type sign-in details, click desktop text, run scripts, use coordinate clicks, record macros, or change remote systems.
- Steps that open higher-risk local apps or admin pages are behind explicit confirmation.
- Environment metadata includes required capabilities and variable hints so Doctor can explain local setup requirements before a run.

Validate and dry-run from the repository root before copying or adapting a template:

```powershell
python -m setpiece validate .\setpiece\sample_recipes\support_triage_workspace.yaml
python -m setpiece dry-run .\setpiece\sample_recipes\support_triage_workspace.yaml
python -m setpiece doctor .\setpiece\sample_recipes\support_triage_workspace.yaml --no-strict
```

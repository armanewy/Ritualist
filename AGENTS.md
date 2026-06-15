# Ritualist Development Notes

- Keep workflow parsing and execution cross-platform.
- Keep Windows UI Automation imports lazy and inside adapter methods.
- Do not add recipe actions that execute arbitrary Python, shell snippets, or JavaScript.
- Tests should use fake adapters and must not require a Windows desktop session.
- Use explicit confirmation gates for risky desktop actions.

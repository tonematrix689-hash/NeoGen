# Genesis

Genesis is an AI operating system kernel built around services, capabilities, and applications.

The kernel owns runtime startup, shutdown, logging, events, dependency injection, service discovery,
lifecycle orchestration, and health reporting. AI providers, memory, permissions, filesystems,
terminals, and desktop applications are capabilities or services layered on top of the kernel.

## Local validation

```powershell
python -m unittest discover -s tests
python -m genesis.app.kernel.main
```

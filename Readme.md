# MarimoTank, a peltier-cooled marimo tank

## Architecture
The marimo cooler is managed by 5 modular components. Only GPIOService needs to be run on the pi itself, but I chose to put all on the pi.

There are multiple reasons for the modular architecture:
1. The `TempManager` component contains the minimal set of features required for temperature regulation, in order to have maximul stability. Any non-core features must be abstracted away.
2. If any module crashes, the failure is contained.
3. Specific parts of the application can be down for updates without affecting the rest of the system. 

### Components
**GPIOService** is a lower level service which manages reads and writes to peripherals connected to the pi. Individual applications do not all interface on their own as multiple applications controlling the GPIO concurrently is unsafe. Uses socker to set up a low-level TCP API similar to a REST api but with less overhead.

**TempManager** is a service which interfaces with GPIOService to regulate temperature. It is the core functionality of the marimo tank. Receives updates through a FastAPI interface.

**WebManager** is a react webapp which provides a webpage frontend for the marimo tank. It interfaces with:
- TempManager to allow for changing settings
- LogService to show historical data
- GPIOService for live temperature and direct peltier/fan control provided TempManager is turned off

It is compiled then served thru Flask.

**LogService** Stores temperature and peltier & fan on/off logs thru GPIOService, can be queried to retrieve logs (FastAPI).

**MarimoWatcher** Sends alerts through telegram when services are down or temperature exceeds 25C for 30 minutes.



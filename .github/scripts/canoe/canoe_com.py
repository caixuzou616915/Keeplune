"""
canoe_com.py
============
Core CANoe COM Automation Interface wrapper (Windows only).

PURPOSE
-------
Provides the single shared connection object used by every other module in
this package.  All other modules receive a ``CANoeConnection`` instance as
their first argument — they never open COM themselves.

MULTI-AGENT ROLE
----------------
This is the **infrastructure layer**.  An orchestrating agent creates one
``CANoeConnection``, passes it down to task-specific subagents or function
calls, and stops the measurement at the end of the session.

DEPENDENCIES
------------
- pywin32 >= 306  (pip install pywin32)
- Vector CANoe installed on the same Windows machine
- CANoe must be open (with a .cfg loaded) before connect() is called

PUBLIC API
----------
Class CANoeConnection:
  connect()                 -- Attach to an already-running CANoe instance
  launch(cfg_path, visible) -- Launch a new instance and load a .cfg
  quit()                    -- Close the CANoe instance
  start_measurement()       -- Start the simulation / measurement
  stop_measurement()        -- Stop the simulation / measurement
  is_running  (property)    -- True if measurement is active
  app         (property)    -- Raw CANoe.Application COM object
  system      (property)    -- CANoe.Application.System (SysVar root)
  environment (property)    -- CANoe.Application.Environment (EnvVar root)
  measurement (property)    -- CANoe.Application.Measurement
  networks    (property)    -- CANoe.Application.Networks
  configuration (property)  -- CANoe.Application.Configuration
  config_path()             -- Return path of the loaded .cfg file

Exception CANoeError(RuntimeError):
  Raised for all COM interaction failures.
"""

import win32com.client
from typing import Optional


class CANoeError(RuntimeError):
    """Raised for all CANoe COM interaction failures."""


class CANoeConnection:
    """
    Manages a COM connection to a CANoe instance.

    Usage (attach to running instance):
        conn = CANoeConnection()
        conn.connect()

    Usage (launch fresh + open config):
        conn = CANoeConnection()
        conn.launch(r"C:\\MyProject\\MyProject.cfg")
    """

    _COM_CLASS = "CANoe.Application"

    def __init__(self) -> None:
        self._app = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Attach to an already-running CANoe instance."""
        try:
            self._app = win32com.client.Dispatch(self._COM_CLASS)
        except Exception as exc:
            raise CANoeError(
                f"Could not connect to CANoe COM server. "
                f"Is CANoe running and is pywin32 installed? Detail: {exc}"
            ) from exc

    def launch(self, cfg_path: Optional[str] = None, visible: bool = True) -> None:
        """
        Launch a new CANoe instance, optionally loading a configuration file.

        Args:
            cfg_path: Absolute path to a .cfg file (optional).
            visible:  Show the CANoe window (default True).
        """
        try:
            self._app = win32com.client.DispatchEx(self._COM_CLASS)
            self._app.Visible = visible
            if cfg_path:
                # Open(path, auto_save=False, prompt_user=False)
                self._app.Open(cfg_path, False, False)
        except Exception as exc:
            raise CANoeError(f"Failed to launch CANoe: {exc}") from exc

    def quit(self) -> None:
        """Close the CANoe instance gracefully."""
        self._require_app()
        try:
            self._app.Quit()
        except Exception as exc:
            raise CANoeError(f"Failed to quit CANoe: {exc}") from exc
        finally:
            self._app = None

    # ------------------------------------------------------------------
    # Measurement control
    # ------------------------------------------------------------------

    def start_measurement(self) -> None:
        """Start the CANoe measurement (simulation)."""
        self._require_app()
        try:
            if not self._app.Measurement.Running:
                self._app.Measurement.Start()
        except Exception as exc:
            raise CANoeError(f"Failed to start measurement: {exc}") from exc

    def stop_measurement(self) -> None:
        """Stop the CANoe measurement."""
        self._require_app()
        try:
            if self._app.Measurement.Running:
                self._app.Measurement.Stop()
        except Exception as exc:
            raise CANoeError(f"Failed to stop measurement: {exc}") from exc

    @property
    def is_running(self) -> bool:
        """True if measurement is currently active."""
        self._require_app()
        return bool(self._app.Measurement.Running)

    # ------------------------------------------------------------------
    # Low-level COM object accessors
    # ------------------------------------------------------------------

    @property
    def app(self):
        """Raw CANoe.Application COM object (use sparingly)."""
        self._require_app()
        return self._app

    @property
    def system(self):
        """COM object: CANoe.Application.System (SysVars root)."""
        return self.app.System

    @property
    def environment(self):
        """COM object: CANoe.Application.Environment (DBC env vars)."""
        return self.app.Environment

    @property
    def measurement(self):
        """COM object: CANoe.Application.Measurement."""
        return self.app.Measurement

    @property
    def networks(self):
        """COM object: CANoe.Application.Networks."""
        return self.app.Networks

    @property
    def configuration(self):
        """COM object: CANoe.Application.Configuration."""
        return self.app.Configuration

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def config_path(self) -> str:
        """Return the path to the currently loaded .cfg file."""
        try:
            return self.app.Configuration.FullName
        except Exception as exc:
            raise CANoeError(f"Could not retrieve config path: {exc}") from exc

    def _require_app(self) -> None:
        if self._app is None:
            raise CANoeError(
                "Not connected to CANoe. Call connect() or launch() first."
            )

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        pass  # do not quit automatically — measurement may still be running

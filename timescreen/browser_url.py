"""Legge l'indirizzo della scheda attiva dalla barra del browser (UI Automation).

Funziona con Chrome, Edge, Brave, Firefox e simili: la barra degli indirizzi
è il primo campo di testo della finestra. Serve comtypes; se manca, o se il
browser non risponde, si torna al riconoscimento dal titolo.
"""

from __future__ import annotations

import logging

log = logging.getLogger("timescreen.logger")

_uia = None
_edit_condition = None
_UIA = None
_unavailable = False


def _init() -> bool:
    global _uia, _edit_condition, _UIA, _unavailable
    if _uia is not None:
        return True
    if _unavailable:
        return False
    try:
        import comtypes.client

        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as UIA

        _uia = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
        _edit_condition = _uia.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, UIA.UIA_EditControlTypeId)
        _UIA = UIA
        return True
    except Exception:
        log.warning("UI Automation non disponibile: i siti si riconoscono solo dal titolo", exc_info=True)
        _unavailable = True
        return False


def warm_up() -> bool:
    """Prepara UI Automation all'avvio del logger, così la prima scheda non aspetta."""
    ok = _init()
    if ok:
        log.info("lettura degli indirizzi dei browser pronta")
    return ok


def address_bar(hwnd: int) -> str | None:
    """Il testo della barra degli indirizzi della finestra, o None."""
    if not _init():
        return None
    try:
        element = _uia.ElementFromHandle(hwnd)
        edit = element.FindFirst(_UIA.TreeScope_Descendants, _edit_condition)
        if not edit:
            return None
        pattern = edit.GetCurrentPattern(_UIA.UIA_ValuePatternId)
        if not pattern:
            return None
        value = pattern.QueryInterface(_UIA.IUIAutomationValuePattern).CurrentValue
        return value or None
    except Exception:
        # finestra chiusa nel frattempo, browser occupato...: si riprova al prossimo cambio
        return None

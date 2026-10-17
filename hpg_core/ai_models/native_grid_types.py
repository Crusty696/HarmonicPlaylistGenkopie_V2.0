"""Gemeinsame ctypes-Vertraege fuer Rekordbox-Beatgrid-Zeilen."""
import ctypes as ct


class Triple(ct.Structure):
    _fields_ = [('pos', ct.c_int32), ('numBar', ct.c_int32), ('bpm', ct.c_int32)]

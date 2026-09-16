"""Repositories: the only place the app reads or writes stored data.

One repository per thing that is stored, each answering with models:

    model_catalogue_repository   the field notes in app/data/model/notes/

A repository may import app.models. It must not import Flask or a service — the
arrow points one way (see tests/test_layers.py):

    view -> controller -> service -> repository
                  |           |
                  +-- model --+
"""

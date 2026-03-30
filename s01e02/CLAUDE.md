# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A simple Python script that fetches location data from the ag3nts.org hub API. No dependencies beyond the Python standard library.

## Running

```bash
python main.py
```

Requires `AG3NTS_KEY` environment variable, loaded from `.env` file (format: `AG3NTS_KEY=<key>`).

## Architecture

- `main.py` — Single-file application. Custom `load_dotenv` parses `.env` without third-party packages. Fetches JSON from `https://hub.ag3nts.org/data/{key}/findhim_locations.json` and prints it.
- `.env` — Contains the `AG3NTS_KEY` secret. Do not commit or share.

# nudle/intents/gag.py

**Role:** Intent handler for hardcoded joke/personality responses.

## Overview

A simple trigger-response map (`GAG_MAP`) of phrases to lists of possible replies.  
`handle(text)` picks a random response from the matching trigger's list.

## Triggers

- "who's your daddy"
- "why are you stupid"
- "are you dumb"
- "you suck"
- "do you love me"
- "what's your favorite color"
- "you stink"

## Intent Interface

`can_handle(text)` checks if any `GAG_MAP` key is a substring of the lowercased input.  
`handle(text)` returns `None` if no trigger matches (defensive fallback).

## Notes

This module is listed last in `main.py`'s intent chain, so it only fires if no other module claimed the utterance. It adds personality without interfering with functional commands.

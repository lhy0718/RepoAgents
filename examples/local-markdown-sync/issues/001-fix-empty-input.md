---
id: 1
title: Fix empty input crash
labels:
  - bug
comments:
  - author: alice
    body: Please keep the parser behavior stable for non-empty input.
---

Calling `parse_items("")` should return an empty list instead of `[""]`.

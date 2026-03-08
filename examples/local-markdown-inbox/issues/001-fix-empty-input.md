---
id: 1
number: 1
title: Fix empty input crash
labels:
  - bug
comments:
  - author: alice
    body: Please keep the fix small.
state: open
---

Calling `parse_items("")` should return an empty list instead of a blank item.

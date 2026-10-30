# Overview
JSON Process is a group of tools able to insert, delete, replace and parse within a JSON data structure.

# Configure
## JSON Insert
JSON Insert tool adds a new value to a JSON object.

![](./_assets/json_insert.png)

## JSON Delete
JSON Delete tool deletes element in a JSON data sturcture.
Array elements are deleted by their JSONPath positions, including when equal values appear more than once.
For example, deleting `$.items[2]` from `{"items": [1, 2, 1]}` returns `{"items": [1, 2]}`.
![](./_assets/json_delete.png)

## JSON Parse
JSON Parse tool converts a JSON string into a JavaScript object or a Python dictionary, depending on the language being used.
![](./_assets/json_parse.png)

## JSON Replace
JSON Replace tool replaces values within a JSON object.
![](./_assets/json_replace.png)
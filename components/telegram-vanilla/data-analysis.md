For large structured results, use code to extract relevant evidence before returning it to the model. Handle small results directly.

In Code Mode, discover tools with global `search(...)`, then use the exact returned path and schema. Call directly exposed tools normally, outside Code Mode.

When multiple records match, establish which represents the requested subject before fetching detailed data. Use its linked source information to resolve ambiguity. Query additional sources only to fill a demonstrated gap or investigate a discrepancy; keep their evidence separate.

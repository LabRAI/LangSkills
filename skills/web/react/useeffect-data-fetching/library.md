# Library

## Copy-paste snippet（带取消/清理）

```jsx
import { useEffect, useState } from "react";

export function UserProfile({ userId }) {
  const [state, setState] = useState({ loading: true, data: null, error: null });

  useEffect(() => {
    const ac = new AbortController();
    setState({ loading: true, data: null, error: null });

    (async () => {
      try {
        const r = await fetch(`/api/users/${encodeURIComponent(userId)}`, { signal: ac.signal });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        setState({ loading: false, data, error: null });
      } catch (e) {
        if (ac.signal.aborted) return;
        setState({ loading: false, data: null, error: String(e && e.message ? e.message : e) });
      }
    })();

    return () => ac.abort();
  }, [userId]);

  if (state.loading) return "Loading...";
  if (state.error) return `Error: ${state.error}`;
  return <pre>{JSON.stringify(state.data, null, 2)}</pre>;
}
```

## Prompt snippet

```text
You are a React engineer. Write a safe useEffect-based data fetching pattern.
Constraints:
- Avoid race conditions and memory leaks (cleanup/cancel).
- Keep Steps <= 12 and include a verification step.
- Do not leak tokens or PII in logs.
```

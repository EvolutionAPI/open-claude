# @evoapi/evonexus-ui

UI primitives for [EvoNexus](https://github.com/EvolutionAPI/evo-nexus) plugin authors.

## Installation

```bash
npm install @evoapi/evonexus-ui react react-dom
```

## Components

- `Button`, `Card`, `Modal`, `Toast`, `Input`, `Select`, `Checkbox` — base primitives
- `ErrorBoundary` — render error catcher (host wraps each plugin route automatically)
- `<SchemaForm>` — JSON-Schema-driven form with Ajv validation
- `<SchemaTable>` — declarative table with sorting

## Usage

```tsx
import { SchemaForm, Button } from "@evoapi/evonexus-ui";
import "@evoapi/evonexus-ui/tokens.css";

const schema = {
  type: "object",
  properties: {
    name: { type: "string", minLength: 1 },
    status: { type: "string", enum: ["active", "archived"] }
  },
  required: ["name"]
};

export function MyForm() {
  return <SchemaForm schema={schema} onSubmit={(values) => console.log(values)} />;
}
```

## License

MIT — see [LICENSE](./LICENSE).

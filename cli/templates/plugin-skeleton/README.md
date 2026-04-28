# __NAME__

A v2 plugin for [EvoNexus](https://github.com/EvolutionAPI/evo-nexus).

## Development

```bash
# Install dependencies (from monorepo root, or point the workspace to @evonexus/ui)
npm install

# Build once
npm run build

# Watch mode (rebuild on save)
npm run dev

# Or use the EvoNexus CLI dev command from the plugin directory:
npx @evoapi/evo-nexus plugin dev
```

## Validate

```bash
npx @evoapi/evo-nexus plugin validate .
```

## Pack for distribution

```bash
npx @evoapi/evo-nexus plugin pack
# Produces: __SLUG__-0.1.0.tgz + __SLUG__-0.1.0.tgz.sha256
```

## Install into EvoNexus

```bash
npx @evoapi/evo-nexus plugin install https://github.com/your-org/__SLUG__
# Or from a local tarball:
npx @evoapi/evo-nexus plugin install ./__SLUG__-0.1.0.tgz
```

## Capabilities

- `agents` — example agent in `agents/`
- `sql_migrations` — dialect-aware SQL (`install.sqlite.sql` + `install.postgres.sql`)
- `ui_pages` — items CRUD page using `<SchemaForm>` + `<SchemaTable>`
- `widgets` — summary widget on the home screen
- `readonly_data` / `writable_data` — items resource

## License

MIT

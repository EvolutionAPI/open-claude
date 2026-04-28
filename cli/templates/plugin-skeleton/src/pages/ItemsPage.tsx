import { SchemaForm, SchemaTable } from '@evoapi/evonexus-ui'

const RESOURCE_ID = '__SLUG___items'

// CRUD page for the items resource.
// SchemaForm drives the create/edit form from writable_data.json_schema.
// SchemaTable renders the list with inline actions.
// Total body below: aim for ≤ 45 LOC excluding imports.
export function ItemsPage() {
  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-semibold text-text-primary">Items</h1>

      <SchemaForm
        resourceId={RESOURCE_ID}
        onSuccess={() => {
          // SchemaTable auto-refreshes via internal invalidation
        }}
      />

      <SchemaTable
        resourceId={RESOURCE_ID}
        columns={['name', 'description', 'active']}
      />
    </div>
  )
}

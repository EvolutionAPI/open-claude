import { Card, CardBody } from '@evonexus/ui'
import { useEffect, useState } from 'react'

interface CountRow { count: number }

// Home-screen widget — reads item_count from readonly_data.
export function SummaryWidget() {
  const [count, setCount] = useState<number | null>(null)

  useEffect(() => {
    fetch('/api/plugins/__SLUG__/data/item_count')
      .then((r) => r.json())
      .then((rows: CountRow[]) => setCount(rows[0]?.count ?? 0))
      .catch(() => setCount(null))
  }, [])

  return (
    <Card>
      <CardBody>
        <p className="text-text-secondary text-sm">Total items</p>
        <p className="text-2xl font-bold text-evo-green">
          {count === null ? '—' : count}
        </p>
      </CardBody>
    </Card>
  )
}

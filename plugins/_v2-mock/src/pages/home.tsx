import { Button, Card, CardHeader, CardBody } from '@evonexus/ui'
import { usePluginNavigation } from '@evonexus/ui'

export default function HomePage({ slug }: { slug: string }) {
  const { navigate } = usePluginNavigation()
  return (
    <Card>
      <CardHeader>v2 Mock Plugin</CardHeader>
      <CardBody>
        <p>slug: {slug}</p>
        <Button onClick={() => navigate('/plugins')}>All plugins</Button>
      </CardBody>
    </Card>
  )
}

import type { LucideIcon } from "lucide-react";
import { Layout } from "@/components/Layout";
import { Card, CardBody } from "@/components/ui/Card";

export function Placeholder({
  title,
  description,
  icon: Icon,
  body,
}: {
  title: string;
  description?: string;
  icon: LucideIcon;
  body: string;
}) {
  return (
    <Layout title={title} description={description}>
      <Card>
        <CardBody className="py-16 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-ink-100 dark:bg-ink-700">
            <Icon className="h-5 w-5 text-ink-500" />
          </div>
          <h3 className="text-lg font-semibold tracking-tight">Coming up next</h3>
          <p className="mx-auto mt-1.5 max-w-md text-sm text-ink-500">{body}</p>
        </CardBody>
      </Card>
    </Layout>
  );
}

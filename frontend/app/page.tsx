


import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import Link from "next/link"

export default function Home() {
  return (
    <main className="min-h-screen w-full bg-neutral-100">
      <div className="flex min-h-screen flex-col items-center justify-center p-4">
        <div className="max-w-md w-full">
          <Card className="bg-white shadow-lg">
            <CardHeader className="text-center">
              <CardTitle className="text-2xl">CrowdResQ Control</CardTitle>
              <CardDescription>AI-assisted event crowd monitoring</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Button asChild className="w-full">
                <Link href="/signin">Sign In</Link>
              </Button>
              <Button asChild variant="outline" className="w-full">
                <Link href="/signup">Sign Up</Link>
              </Button>
            </CardContent>
            <CardFooter className="text-center text-sm text-muted-foreground">
              Live feed, density analysis, and stampede-risk alerts for event authorities
            </CardFooter>
          </Card>
        </div>
      </div>
    </main>
  )
}


import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { LogOut, Shield } from "lucide-react";

export default function DashboardPage() {
  const { user, logout } = useAuth();

  return (
    <div className="flex min-h-svh items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Shield className="size-6 text-primary" />
            <CardTitle className="text-2xl">You are logged in</CardTitle>
          </div>
          <CardDescription>
            Welcome back, <span className="font-semibold">{user?.username}</span>!
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          <p className="text-muted-foreground">
            This is your dashboard. You'll be able to build stuff here later.
          </p>
          <Button variant="outline" onClick={logout}>
            <LogOut data-icon="inline-start" />
            Logout
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

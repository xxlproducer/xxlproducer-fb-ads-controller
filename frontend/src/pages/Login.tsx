import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuth } from "@/lib/auth";
import { getApiErrorMessage } from "@/lib/api";

export function Login() {
  const { setupRequired, login, setup } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const isSetup = setupRequired === true;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (isSetup && password !== confirm) {
      toast.error("Passwords do not match");
      return;
    }
    setSubmitting(true);
    try {
      if (isSetup) {
        await setup(username, password);
        toast.success("Account created");
      } else {
        await login(username, password);
      }
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Login failed"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-ink-50 via-white to-ink-100 px-6 dark:from-ink-900 dark:via-ink-800 dark:to-ink-900">
      <div className="w-full max-w-sm animate-slide-up">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-ink-900 to-ink-700 text-white shadow-card">
            <span className="text-sm font-bold">FB</span>
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {isSetup ? "Create your account" : "Welcome back"}
          </h1>
          <p className="mt-1.5 text-sm text-ink-500">
            {isSetup
              ? "First-time setup — choose a username and password"
              : "Sign in to your local Ads Controller"}
          </p>
        </div>

        <form
          onSubmit={onSubmit}
          className="space-y-3 rounded-3xl bg-white p-6 shadow-card dark:bg-ink-800/60 dark:ring-1 dark:ring-ink-700/60"
        >
          <Input
            label="Username"
            name="username"
            type="text"
            autoComplete="username"
            autoFocus
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            minLength={2}
          />
          <Input
            label="Password"
            name="password"
            type="password"
            autoComplete={isSetup ? "new-password" : "current-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={4}
          />
          {isSetup && (
            <Input
              label="Confirm password"
              name="confirm"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              minLength={4}
            />
          )}
          <Button
            type="submit"
            size="lg"
            loading={submitting}
            className="w-full"
          >
            {isSetup ? "Create account" : "Sign in"}
          </Button>
        </form>

        <p className="mt-6 text-center text-xs text-ink-500">
          Stored locally on your machine. Nothing leaves this PC.
        </p>
      </div>
    </div>
  );
}

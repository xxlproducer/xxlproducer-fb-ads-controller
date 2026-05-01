import { Navigate, Route, Routes } from "react-router-dom";
import { Rocket } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { Login } from "@/pages/Login";
import { Tokens } from "@/pages/Tokens";
import { Dashboard } from "@/pages/Dashboard";
import { BulkActions } from "@/pages/BulkActions";
import { Placeholder } from "@/pages/Placeholder";

function FullScreenLoader() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-ink-300 border-t-ink-700" />
    </div>
  );
}

export default function App() {
  const { user, loading } = useAuth();

  if (loading) return <FullScreenLoader />;

  if (!user) {
    return (
      <Routes>
        <Route path="*" element={<Login />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/tokens" element={<Tokens />} />
      <Route path="/bulk" element={<BulkActions />} />
      <Route
        path="/launch"
        element={
          <Placeholder
            title="Autozaliv"
            description="Launch Sales / Purchase campaigns across multiple ad accounts"
            icon={Rocket}
            body="3-step wizard: pick template → pick accounts → upload creatives. Currently in design — UI lands next."
          />
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

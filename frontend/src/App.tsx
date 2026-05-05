import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { Login } from "@/pages/Login";
import { Tokens } from "@/pages/Tokens";
import { Dashboard } from "@/pages/Dashboard";
import { BulkActions } from "@/pages/BulkActions";
import { Autozaliv } from "@/pages/Autozaliv";
import { Creatives } from "@/pages/Creatives";

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
      <Route path="/launch" element={<Autozaliv />} />
      <Route path="/creatives" element={<Creatives />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

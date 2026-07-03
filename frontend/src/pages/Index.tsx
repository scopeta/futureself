import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import WelcomeScreen from "@/components/WelcomeScreen";
import ChatInterface from "@/components/ChatInterface";
import { clearSession, fetchBlueprint, hasSession } from "@/lib/api";

const Index = () => {
  const navigate = useNavigate();
  const [view, setView] = useState<"loading" | "welcome" | "chat">("loading");

  useEffect(() => {
    if (!hasSession()) {
      setView("welcome");
      return;
    }
    fetchBlueprint()
      .then((bp) => {
        if (!bp.onboarded) {
          navigate("/onboarding", { replace: true });
        } else {
          setView("chat");
        }
      })
      .catch(() => {
        // Stale/invalid token — send the user back to the welcome screen.
        clearSession();
        setView("welcome");
      });
  }, [navigate]);

  if (view === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-primary" />
      </div>
    );
  }

  if (view === "welcome") {
    return <WelcomeScreen onStart={() => navigate("/login")} />;
  }

  return <ChatInterface />;
};

export default Index;

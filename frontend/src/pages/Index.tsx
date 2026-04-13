import { useState } from "react";
import WelcomeScreen from "@/components/WelcomeScreen";
import ChatInterface from "@/components/ChatInterface";
import { createSession, hasSession } from "@/lib/api";

const Index = () => {
  // Skip welcome screen if a session is already stored in localStorage
  const [started, setStarted] = useState(hasSession());

  const handleStart = async () => {
    await createSession();
    setStarted(true);
  };

  if (!started) {
    return <WelcomeScreen onStart={handleStart} />;
  }

  return <ChatInterface />;
};

export default Index;

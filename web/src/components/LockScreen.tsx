import React, { useState, useEffect, useRef } from "react";
import { api } from "../api";

interface LockScreenProps {
  configured: boolean;
  onAuthenticated: () => void;
}

export default function LockScreen({ configured, onAuthenticated }: LockScreenProps) {
  const [pin, setPin] = useState("");
  const [confirmPin, setConfirmPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // Focus input on load
    inputRef.current?.focus();
  }, []);

  const handleUnlock = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!pin) return;

    setLoading(true);
    setError(null);

    try {
      if (!configured) {
        if (pin.length < 4) {
          setError("PIN must be at least 4 digits");
          setLoading(false);
          return;
        }
        if (pin !== confirmPin) {
          setError("PINs do not match");
          setLoading(false);
          return;
        }
        const res = await api.authSetup(pin);
        if (res.token) {
          localStorage.setItem("mymonee_auth_token", res.token);
        }
        onAuthenticated();
      } else {
        const res = await api.authLogin(pin);
        if (res.token) {
          localStorage.setItem("mymonee_auth_token", res.token);
        }
        onAuthenticated();
      }
    } catch (err: any) {
      setError(err.message || "Incorrect PIN");
      setPin("");
      inputRef.current?.focus();
    } finally {
      setLoading(false);
    }
  };

  const handleKeypadPress = (val: string) => {
    setError(null);
    if (val === "backspace") {
      setPin((prev) => prev.slice(0, -1));
    } else if (val === "clear") {
      setPin("");
    } else {
      if (pin.length < 12) {
        const newPin = pin + val;
        setPin(newPin);
      }
    }
  };

  return (
    <div
      style={{
        minHeight: "100dvh",
        width: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--bg)",
        padding: "16px",
        boxSizing: "border-box",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "380px",
          margin: "auto",
          background: "var(--surface)",
          border: "1px solid var(--line)",
          borderRadius: "16px",
          boxShadow: "0 4px 24px rgba(0, 0, 0, 0.05)",
          padding: "32px 24px",
          textAlign: "center",
          boxSizing: "border-box",
        }}
      >
        {/* App Logo */}
        <div style={{ marginBottom: "16px", display: "flex", justifyContent: "center" }}>
          <img
            src="/logo.png"
            alt="MyMonee Logo"
            style={{
              width: "56px",
              height: "56px",
              objectFit: "contain",
              background: "transparent",
              filter: "drop-shadow(0 2px 8px rgba(0, 0, 0, 0.08))",
            }}
          />
        </div>

        <h1 style={{ fontSize: "1.25rem", fontWeight: 700, margin: "0 0 20px 0", color: "var(--ink)" }}>
          {!configured ? "Secure Your MyMonee" : "MyMonee is Locked"}
        </h1>

        <form
          method="post"
          action="#"
          onSubmit={handleUnlock}
          style={{ display: "flex", flexDirection: "column", gap: "16px" }}
        >
          {/* Visually hidden for Safari Keychain credential association */}
          <input
            id="mymonee-username"
            type="text"
            name="username"
            defaultValue="Gaurav"
            autoComplete="username"
            tabIndex={-1}
            aria-hidden="true"
            style={{
              position: "absolute",
              width: "1px",
              height: "1px",
              padding: 0,
              margin: "-1px",
              overflow: "hidden",
              clip: "rect(0,0,0,0)",
              border: 0,
              opacity: 0,
            }}
          />

          <div>
            <input
              ref={inputRef}
              id="master-pin"
              name="password"
              type="password"
              autoComplete={!configured ? "new-password" : "current-password"}
              placeholder="••••••"
              value={pin}
              onChange={(e) => {
                setError(null);
                setPin(e.target.value);
              }}
              style={{
                width: "100%",
                fontSize: "1.5rem",
                textAlign: "center",
                letterSpacing: "0.3em",
                padding: "10px 14px",
                borderRadius: "8px",
                border: error ? "1.5px solid var(--danger, #ef4444)" : "1px solid var(--line)",
                background: "var(--bg)",
                color: "var(--ink)",
                outline: "none",
              }}
            />
          </div>

          {!configured && (
            <div>
              <input
                type="password"
                inputMode="numeric"
                pattern="[0-9]*"
                autoComplete="new-password"
                placeholder="Confirm PIN"
                value={confirmPin}
                onChange={(e) => {
                  setError(null);
                  setConfirmPin(e.target.value);
                }}
                style={{
                  width: "100%",
                  fontSize: "1.2rem",
                  textAlign: "center",
                  letterSpacing: "0.3em",
                  padding: "12px 16px",
                  borderRadius: "10px",
                  border: "1px solid var(--line)",
                  background: "var(--bg)",
                  color: "var(--ink)",
                  outline: "none",
                }}
              />
            </div>
          )}

          {error && (
            <div style={{ color: "var(--danger, #ef4444)", fontSize: "0.82rem", fontWeight: 600 }}>
              {error}
            </div>
          )}

          {/* Quick On-Screen Keypad for Mobile / Tablet */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: "8px",
              marginTop: "8px",
            }}
          >
            {["1", "2", "3", "4", "5", "6", "7", "8", "9", "C", "0", "⌫"].map((btn) => (
              <button
                key={btn}
                type="button"
                className="btn quiet"
                onClick={() => {
                  if (btn === "C") handleKeypadPress("clear");
                  else if (btn === "⌫") handleKeypadPress("backspace");
                  else handleKeypadPress(btn);
                }}
                style={{
                  padding: "12px 0",
                  fontSize: "1.15rem",
                  fontWeight: 600,
                  borderRadius: "8px",
                  background: "var(--bg)",
                  border: "1px solid var(--line)",
                  color: "var(--ink)",
                  cursor: "pointer",
                }}
              >
                {btn}
              </button>
            ))}
          </div>

          <button
            type="submit"
            className="btn primary"
            disabled={loading || !pin}
            style={{
              marginTop: "8px",
              padding: "14px 20px",
              fontSize: "0.95rem",
              fontWeight: 600,
              width: "100%",
            }}
          >
            {loading ? "Unlocking…" : !configured ? "Save PIN & Unlock" : "Unlock MyMonee"}
          </button>
        </form>

        <div style={{ marginTop: "24px", fontSize: "0.78rem", color: "var(--ink-muted)" }}>
          🔒 Local-First Privacy · Saved directly in Safari Keychain
        </div>
      </div>
    </div>
  );
}

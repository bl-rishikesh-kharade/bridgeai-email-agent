import React from "react";
import { LoaderCircle, LogOut, Mail, Plus } from "lucide-react";

interface NavbarProps {
  email?: string | null;
  busy: boolean;
  switchingAccount: boolean;
  onSwitchAccount: () => void;
  onResetChat: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  email,
  busy,
  switchingAccount,
  onSwitchAccount,
  onResetChat,
}) => {
  return (
    <header className="topbar app-topbar">
      <button
        className="brand"
        type="button"
        onClick={onResetChat}
        aria-label="BridgeAI Email Agent home - start new chat"
        style={{ background: "transparent", border: 0, padding: 0, cursor: "pointer", textAlign: "left" }}
      >
        <span className="brand-mark">
          <Mail size={19} />
        </span>
        <span className="brand-text">
          <strong>BridgeAI</strong>
          <span>Email Agent</span>
        </span>
      </button>
      <div className="topbar-right">
        {email && <span className="connected-account">{email}</span>}
        <button
          className="new-chat-button"
          type="button"
          onClick={onResetChat}
          disabled={busy}
          title="Start a fresh chat"
        >
          <Plus size={14} />
          <span>New chat</span>
        </button>
        <button
          className="switch-account-button"
          type="button"
          onClick={onSwitchAccount}
          disabled={busy || switchingAccount}
          title="Switch connected Google account"
        >
          {switchingAccount ? (
            <LoaderCircle size={14} className="spin" />
          ) : (
            <LogOut size={14} />
          )}
          {switchingAccount ? "Switching…" : "Switch account"}
        </button>
      </div>
    </header>
  );
};

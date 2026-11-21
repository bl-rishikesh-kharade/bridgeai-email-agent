import React from "react";
import { LoaderCircle, LogOut, Mail } from "lucide-react";

interface NavbarProps {
  email?: string | null;
  busy: boolean;
  switchingAccount: boolean;
  onSwitchAccount: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  email,
  busy,
  switchingAccount,
  onSwitchAccount,
}) => {
  return (
    <header className="topbar app-topbar">
      <a className="brand" href="/" aria-label="BridgeAI Email Agent home">
        <span className="brand-mark">
          <Mail size={19} />
        </span>
        <span className="brand-text">
          <strong>BridgeAI</strong>
          <span>Email Agent</span>
        </span>
      </a>
      <div className="topbar-right">
        {email && <span className="connected-account">{email}</span>}
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

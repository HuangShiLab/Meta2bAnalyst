"use client"

import * as React from "react"

interface CollapsibleProps {
  children: React.ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

const CollapsibleContext = React.createContext<{
  open: boolean;
  setOpen: (open: boolean) => void;
}>({ open: false, setOpen: () => {} });

function Collapsible({ children, open: controlledOpen, onOpenChange }: CollapsibleProps) {
  const [uncontrolledOpen, setUncontrolledOpen] = React.useState(false);
  const open = controlledOpen !== undefined ? controlledOpen : uncontrolledOpen;
  const setOpen = (value: boolean) => {
    setUncontrolledOpen(value);
    onOpenChange?.(value);
  };
  return (
    <CollapsibleContext.Provider value={{ open, setOpen }}>
      <div>{children}</div>
    </CollapsibleContext.Provider>
  );
}

function CollapsibleTrigger({ children, asChild }: { children: React.ReactNode; asChild?: boolean }) {
  const { open, setOpen } = React.useContext(CollapsibleContext);
  if (asChild && React.isValidElement(children)) {
    return React.cloneElement(children as React.ReactElement, {
      onClick: () => setOpen(!open),
    } as React.HTMLAttributes<HTMLElement>);
  }
  return <div onClick={() => setOpen(!open)} className="cursor-pointer">{children}</div>;
}

function CollapsibleContent({ children }: { children: React.ReactNode }) {
  const { open } = React.useContext(CollapsibleContext);
  if (!open) return null;
  return <div>{children}</div>;
}

export { Collapsible, CollapsibleTrigger, CollapsibleContent }

"""Speed-X: Interactive CLI Shell and Command Dispatcher."""

import sys
import time
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Initialize all tools and router
from speed_x.config import DEFAULT_COMPUTE_UNITS, is_apple_silicon
from speed_x.core.router import CommandRouter

console = Console()


def print_banner():
    arch_str = "Apple Silicon (ANE / GPU)" if is_apple_silicon() else "Intel x86_64 (CPU Engine)"
    console.print(
        Panel(
            f"[bold cyan]Speed-X[/bold cyan] - [dim]Private AI Control Layer for macOS[/dim]\n"
            f"[dim]Engine:[/dim] [green]{arch_str}[/green] · [dim]Compute Units:[/dim] [yellow]{DEFAULT_COMPUTE_UNITS}[/yellow]\n"
            f"[dim]Bilingual:[/dim] English & Kiswahili / Sheng code-switching\n"
            f"[dim]Type 'help', 'tools', or 'exit'[/dim]",
            border_style="cyan",
        )
    )


def show_tools():
    from speed_x.tools.base import registry

    table = Table(title="Available Tools & Actions", border_style="dim")
    table.add_column("Domain", style="cyan", no_wrap=True)
    table.add_column("Actions", style="green")

    for domain, actions in registry.list_tools().items():
        table.add_row(domain, ", ".join(actions))
    console.print(table)


def run_command(router: CommandRouter, prompt: str):
    start = time.perf_counter()
    resp = router.process(prompt)
    latency_ms = (time.perf_counter() - start) * 1000

    if resp.needs_confirmation:
        console.print(f"[bold yellow][CONFIRM] {resp.confirmation_prompt}[/bold yellow]")
        choice = input("Confirm? (y/N): ").strip().lower()
        if choice == "y":
            start = time.perf_counter()
            resp = router.process(prompt, confirmed=True)
            latency_ms = (time.perf_counter() - start) * 1000
        else:
            console.print("[dim]Action cancelled by user.[/dim]")
            return

    status_icon = "[OK]" if resp.success else "[ERR]"
    color = "green" if resp.success else "red"

    console.print(
        f"[{color}]{status_icon} {resp.message}[/{color}] "
        f"[dim]({latency_ms:.1f}ms · {resp.decision.domain}:{resp.decision.action} · src: {resp.decision.source})[/dim]"
    )


def interactive_loop():
    print_banner()
    router = CommandRouter()

    while True:
        try:
            prompt = console.input("[bold cyan]Laya > [/bold cyan]").strip()
            if not prompt:
                continue
            if prompt.lower() in ("exit", "quit", "q"):
                console.print("[dim]Kwaheri! (Goodbye!)[/dim]")
                break
            if prompt.lower() == "help":
                console.print("[dim]Try commands like:[/dim]")
                console.print("  • [cyan]cheza muziki[/cyan] / [cyan]play music[/cyan]")
                console.print("  • [cyan]ongeza sauti[/cyan] / [cyan]volume up[/cyan]")
                console.print("  • [cyan]fungua Safari[/cyan] / [cyan]open Safari[/cyan]")
                console.print("  • [cyan]funga screen[/cyan] / [cyan]lock screen[/cyan]")
                console.print("  • [cyan]tafuta pdf[/cyan] / [cyan]find pdf[/cyan]")
                console.print("  • [cyan]anza coding[/cyan] / [cyan]start coding[/cyan]")
                console.print("  • [cyan]angalia clipboard[/cyan] / [cyan]read clipboard[/cyan]")
                continue
            if prompt.lower() == "tools":
                show_tools()
                continue

            run_command(router, prompt)

        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Exiting...[/dim]")
            break


def main():
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:]).strip()
        if prompt in ("tools", "--tools"):
            show_tools()
            return
        if prompt in ("help", "--help", "-h"):
            print_banner()
            return
        if prompt in ("menubar", "--menubar"):
            from speed_x.ui.menubar import run_menubar
            console.print("[green]Starting Speed-X Menu Bar app...[/green] (Look at the macOS top status bar)")
            run_menubar()
            return
        if sys.argv[1] == "--json" and len(sys.argv) > 2:
            import json as pyjson
            actual_prompt = " ".join(sys.argv[2:]).strip()
            router = CommandRouter()
            start = time.perf_counter()
            resp = router.process(actual_prompt, confirmed=True)
            latency = (time.perf_counter() - start) * 1000
            print(pyjson.dumps({
                "success": resp.success,
                "message": resp.message,
                "domain": resp.decision.domain,
                "action": resp.decision.action,
                "confidence": resp.decision.confidence,
                "latency_ms": round(latency, 1),
                "source": resp.decision.source,
            }))
            return
        router = CommandRouter()
        run_command(router, prompt)
    else:
        interactive_loop()


if __name__ == "__main__":
    main()

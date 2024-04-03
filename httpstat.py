import argparse
import json
import logging
import os
import requests
import subprocess
import sys
import tempfile
import whois

from rich.console import Console
from rich.rule import Rule
from typing import Optional, Tuple, Union


console = Console()

__version__ = "1.2.2"


env_keys = {
    "SHOW_BODY": "HTTPSTAT_SHOW_BODY",
    "SHOW_WHOIS": "HTTPSTAT_SHOW_WHOIS",
    "SHOW_IP": "HTTPSTAT_SHOW_IP",
    "SHOW_SPEED": "HTTPSTAT_SHOW_SPEED",
    "SAVE_BODY": "HTTPSTAT_SAVE_BODY",
    "CURL_BIN": "HTTPSTAT_CURL_BIN",
    "DEBUG": "HTTPSTAT_DEBUG",
}


def get_env(env_key: str, default: Optional[str] = None) -> str:
    """
    Get the specified key value from the environment variable, or return the default value if it does not exist.

    Args.
        env_key: Environment variable key name.
        default: The default value returned if the specified environment variable does not exist.

    Returns: The value or default value of the environment variable.
        The value or default value of the environment variable.
    """
    return os.environ.get(env_keys[env_key], default)


# get env
show_body = get_env("SHOW_BODY", "false").lower() == "true"
show_whois = get_env("SHOW_WHOIS", "true").lower() == "true"
show_ip = get_env("SHOW_IP", "true").lower() == "true"
show_speed = get_env("SHOW_SPEED", "false").lower() == "true"
save_body = get_env("SAVE_BODY", "true").lower() == "true"
curl_bin = get_env("CURL_BIN", "curl")
is_debug = get_env("DEBUG", "false").lower() == "true"


curl_format = """{
"time_namelookup": %{time_namelookup},
"time_connect": %{time_connect},
"time_appconnect": %{time_appconnect},
"time_pretransfer": %{time_pretransfer},
"time_redirect": %{time_redirect},
"time_starttransfer": %{time_starttransfer},
"time_total": %{time_total},
"speed_download": %{speed_download},
"speed_upload": %{speed_upload},
"remote_ip": "%{remote_ip}",
"remote_port": "%{remote_port}",
"local_ip": "%{local_ip}",
"local_port": "%{local_port}"
}"""


https_template = """
  DNS Lookup   TCP Connection   TLS Handshake   Server Processing   Content Transfer
[   {a0000}  |     {a0001}    |    {a0002}    |      {a0003}      |      {a0004}     ]
             |                |               |                   |                  |
    namelookup:{b0000}        |               |                   |                  |
                        connect:{b0001}       |                   |                  |
                                    pretransfer:{b0002}           |                  |
                                                      starttransfer:{b0003}          |
                                                                                 total:{b0004}
"""

http_template = """
  DNS Lookup   TCP Connection   Server Processing   Content Transfer
[   {a0000}  |     {a0001}    |      {a0003}      |      {a0004}     ]
             |                |                   |                  |
    namelookup:{b0000}        |                   |                  |
                        connect:{b0001}           |                  |
                                      starttransfer:{b0003}          |
                                                                 total:{b0004}
"""


def quit(message: str = None, code: int = 0) -> None:
    """
    Exits the program and displays the specified message.

    Parameters:
    - message: the message to display before exiting (optional).
    - code: The exit code to return (optional).

    Usage:
    - quit() or quit(code=1) or quit(message="reason for quitting").
    """
    if message is not None:
        console.print(message)
    sys.exit(code)


def parse_arguments():
    """
    Define argparse arguments and options
    """
    parser = argparse.ArgumentParser(
        description="httpstat_pro: visualizes `IP Infomation`, `WHOIS Infomation` and `curl(1)` statistics in a way of beauty and clarity."
    )
    parser.add_argument(
        "URL", help="URL to request, could be with or without `http(s)://` prefix"
    )
    parser.add_argument(
        "CURL_OPTIONS",
        nargs="*",
        help="Any curl supported options, except for -w -D -o -S -s, which are already used internally.",
    )
    # parser.add_argument("-h", "--help", action="store_true", help="show help")
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="show version",
    )
    return parser.parse_args()


def get_whois_info(url: str) -> dict:
    """
    Get WHOIS information from the given URL.

    This function first resolves the domain name from the URL and then uses the whois library to query the WHOIS information for the domain.

    Args.
        url (str): The URL to query for WHOIS information.

    Returns.
        dict: The WHOIS information, in dictionary form.
    """
    domain = url.split("//")[-1].split("/")[0].split("?")[0]
    w = whois.whois(domain)
    return w


def run_curl_command(
    curl_bin: str, curl_args: list, url: str
) -> Tuple[Optional[str], Optional[str]]:
    """Execute the curl command and return the result.

    Args.
        curl_bin (str): Path to the curl executable.
        curl_args (list): List of arguments to the curl command.
        url (str): The URL of the request.

    Returns.
        tuple: (output, error message), if successful, error message None.
    """
    cmd = [curl_bin] + curl_args + [url]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, shell=False)
        return output.decode("utf-8"), None
    except subprocess.CalledProcessError as e:
        return None, e.output.decode("utf-8")


def format_time_centered(time_value: Union[float, int]) -> str:
    """
    Format the time data to be center-aligned and add units.

    Args.
        time_value (float or int): time_value.

    Returns.
        str: Formatted string containing the time unit.
    """
    return f"[bold cyan]{str(time_value)+'ms':^7}[/bold cyan]"


def format_time_left_aligned(time_value: Union[float, int]) -> str:
    """
    Format the time data to be left-aligned, and add units.

    Args:
            time_value (float or int): The value of the time.

    Returns:
            str: A formatted string containing a unit of time.
    """
    return f"[bold cyan]{str(time_value)+'ms':<7}[/bold cyan]"


def main():
    args = parse_arguments()

    url = args.URL
    curl_args = args.CURL_OPTIONS

    # configure logging
    if is_debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO
    logging.basicConfig(level=log_level)
    logger = logging.getLogger(__name__)

    # log envs
    logger.debug(
        "Envs:\n%s",
        "\n".join("  {}={}".format(key, get_env(key)) for key in env_keys),
    )
    logger.debug(
        "Flags: %s",
        dict(
            show_body=show_body,
            show_whois=show_whois,
            show_ip=show_ip,
            show_speed=show_speed,
            save_body=save_body,
            curl_bin=curl_bin,
            is_debug=is_debug,
        ),
    )

    # check curl args
    exclude_options = [
        "-w",
        "--write-out",
        "-D",
        "--dump-header",
        "-o",
        "--output",
        "-s",
        "--silent",
    ]
    for i in exclude_options:
        if i in curl_args:
            quit("Error: {} is not allowed in extra curl args".format(i), 1)

    # tempfile for output
    bodyf = tempfile.NamedTemporaryFile(delete=False)
    bodyf.close()

    headerf = tempfile.NamedTemporaryFile(delete=False)
    headerf.close()

    # run cmd
    cmd_env = os.environ.copy()
    cmd_env.update(
        LC_ALL="C",
    )
    curl_args = [
        "-w",
        curl_format,
        "-D",
        headerf.name,
        "-o",
        bodyf.name,
        "-s",
        "-S",
    ] + curl_args

    # Calling the run_curl_command function to get curl_output
    curl_output, curl_error = run_curl_command(curl_bin, curl_args, url)
    if curl_error:
        quit(f"Curl command failed with error: {curl_error}", 1)
    else:
        # parse output
        try:
            curl_result = json.loads(curl_output)
        except ValueError as e:
            quit("Could not decode JSON: {}".format(e), 1)
        for metric in curl_result:
            if metric.startswith("time_"):
                curl_result[metric] = int(curl_result[metric] * 1000)

        # Calculation of time for each stage
        curl_result.update(
            range_dns=curl_result["time_namelookup"],
            range_connection=curl_result["time_connect"]
            - curl_result["time_namelookup"],
            range_ssl=curl_result["time_pretransfer"] - curl_result["time_connect"],
            range_server=curl_result["time_starttransfer"]
            - curl_result["time_pretransfer"],
            range_transfer=curl_result["time_total"]
            - curl_result["time_starttransfer"],
        )

        console.print(Rule(style="#00b294"))

    # whois
    if show_whois:
        console.print("\n", "🔗\ufe0e:", f"[bold #00b294]URL: {url}[/bold #00b294]")
        whois_info = get_whois_info(url)
        console.print(
            "\n",
            "🫣\ufe0e:",
            f"[bold #00b294]WHOIS Infoamtion:[/bold #00b294] \n {whois_info}",
        )
        console.print(Rule(style="#00b294"))

    # ip
    if show_ip:
        s = f"\nConnected to {curl_result['remote_ip']}:{curl_result['remote_port']} from {curl_result['local_ip']}:{curl_result['local_port']}"
        console.print(f"\n {s} \n")

        url = f"http://ip-api.com/json/{curl_result['remote_ip']}"
        response = requests.get(url)
        if response.status_code == 200:
            console.print(
                "\n",
                "🗺️\ufe0e:",
                f"[bold #00b294]Remote IP Infomation:[/bold #00b294] [dim](Powered By ip-api.com)[/dim] \n {json.dumps(response.json(), indent=2)}",
            )
            country = response.json().get("country", "Unknown")
            regionName = response.json().get("regionName", "Unknown")
            city = response.json().get("city", "Unknown")
            remote_ip_location = f"[cyan]{country}[/cyan]--[cyan]{regionName}[/cyan]--[cyan]{city}[/cyan]"
        else:
            remote_ip_location = "Unknown Location"
        console.print(f"\nRemote IP Location: {remote_ip_location}")
        console.print(Rule(style="#00b294"))

    # print header & body summary
    with open(headerf.name, "r") as f:
        headers = f.read().strip()
    # remove header file
    logger.debug("rm header file %s", headerf.name)
    os.remove(headerf.name)

    console.print("\n", "😑\ufe0e:", f"[bold #00b294]Response Headers:[/bold #00b294]")
    for loop, line in enumerate(headers.split("\n")):
        if loop == 0:
            p1, p2 = tuple(line.split("/"))
            console.print(f"[cyan]{p1}[/cyan] / [cyan]{p2}[/cyan]")

        else:
            pos = line.find(":")
            console.print(
                f"[dim]{line[: pos + 1]}[/dim] [cyan]{line[pos + 1 :]}[/cyan]"
            )

    # body
    if show_body:
        body_limit = 1024
        with open(bodyf.name, "r") as f:
            body = f.read().strip()
        body_len = len(body)

        if body_len > body_limit:
            console.print(f"body[:body_limit] [green]...[/green]")
            s = f"[green]Body[/green] [dim white]is truncated ({body_limit} out of {body_len})[/dim white]"
            if save_body:
                s += f", stored in: {bodyf.name}"
            console.print(s)
        else:
            console.print(body)
    else:
        if save_body:
            console.print(
                f"[green]Body[green/] [dim white]stored in: {bodyf.name}[/dim white]"
            )

    # remove body file
    if not save_body:
        logger.debug("rm body file %s", bodyf.name)
        os.remove(bodyf.name)

    # print stat
    if url.startswith("https://"):
        template = https_template
    else:
        template = http_template

    # colorize template first line
    tpl_parts = template.split("\n")
    template = "\n".join(tpl_parts)

    stat = template.format(
        # a
        a0000=format_time_centered(curl_result["range_dns"]),
        a0001=format_time_centered(curl_result["range_connection"]),
        a0002=format_time_centered(curl_result["range_ssl"]),
        a0003=format_time_centered(curl_result["range_server"]),
        a0004=format_time_centered(curl_result["range_transfer"]),
        # b
        b0000=format_time_left_aligned(curl_result["time_namelookup"]),
        b0001=format_time_left_aligned(curl_result["time_connect"]),
        b0002=format_time_left_aligned(curl_result["time_pretransfer"]),
        b0003=format_time_left_aligned(curl_result["time_starttransfer"]),
        b0004=format_time_left_aligned(curl_result["time_total"]),
    )
    console.print("\n", "⏱️\ufe0e:", f"[bold #00b294]HTTP Stat:[/bold #00b294]")
    console.print(stat)
    console.print(Rule(style="#00b294"))
    # speed, originally bytes per second
    if show_speed:
        console.print(
            "speed_download: {:.1f} KiB/s, speed_upload: {:.1f} KiB/s".format(
                curl_result["speed_download"] / 1024, curl_result["speed_upload"] / 1024
            )
        )


if __name__ == "__main__":
    main()

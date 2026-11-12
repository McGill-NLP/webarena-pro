#!/bin/bash
# Sourced by the preseeded entrypoint and reset command.

nextcloud_public_url() {
  local host_port public_host public_scheme inferred

  host_port="${WP_NEXTCLOUD_HOST_PORT:-8080}"
  case "$host_port" in
    ''|*[!0-9]*) host_port="8080" ;;
  esac

  public_host="${WP_NEXTCLOUD_HOST:-${WP_PUBLIC_HOST:-localhost}}"
  public_scheme="${WP_NEXTCLOUD_SCHEME:-${WP_PUBLIC_SCHEME:-http}}"
  public_host="${public_host%/}"
  public_scheme="${public_scheme%://}"
  public_scheme="${public_scheme%:}"

  if [[ "$public_host" == *"://"* ]]; then
    inferred="$public_host"
  elif [[ "$public_host" == *":"* ]]; then
    inferred="${public_scheme}://${public_host}"
  else
    inferred="${public_scheme}://${public_host}:${host_port}"
  fi

  echo "${WP_NEXTCLOUD_URL:-${NEXTCLOUD_EXTERNAL_URL:-$inferred}}" | sed 's:/*$::'
}

configure_richdocuments_url() {
  local public_url
  public_url="$1"
  # PHP reads argv, so URLs cannot become shell code.
  if [ "$(id -u)" = 0 ]; then
    runuser -u www-data -- php /seedDir/configure-office.php "$public_url"
  else
    php /seedDir/configure-office.php "$public_url"
  fi
}

configure_office_loopback() {
  # Built-in CODE's status endpoint uses the same origin as the browser. For
  # HTTP deployments, route only this container's own public hostname back to
  # Apache; worker hostnames must never resolve through another worker.
  local hostname scheme
  read -r hostname scheme < <(php -r '$u=parse_url($argv[1]); echo ($u["host"] ?? "") . " " . ($u["scheme"] ?? "") . "\n";' "$(nextcloud_public_url)")
  if [ "$scheme" = http ] && [[ "$hostname" =~ ^[a-zA-Z0-9.-]+$ ]] && [[ ! "$hostname" =~ ^[0-9.]+$ ]]; then
    if ! grep -Fq "127.0.0.1 $hostname # webarena-office" /etc/hosts; then
      printf '\n127.0.0.1 %s # webarena-office\n' "$hostname" >> /etc/hosts
    fi
  fi
}

stop_builtin_office() {
  local pidfile pid
  rm -f /tmp/webarena-office.ready /tmp/webarena-office.failed
  pidfile=/tmp/richdocumentscode-33/coolwsd.pid
  if [ -f "$pidfile" ]; then
    pid="$(cat "$pidfile")"
    if [[ "$pid" =~ ^[0-9]+$ ]] && [ "$(cat "/proc/$pid/comm" 2>/dev/null || true)" = coolwsd ] && [ "$(stat -c %u "/proc/$pid")" = 33 ]; then
      kill -TERM "$pid"
      for _i in $(seq 1 30); do
        kill -0 "$pid" 2>/dev/null || break
        [ "$(awk '{print $3}' "/proc/$pid/stat" 2>/dev/null || true)" != Z ] || break
        sleep 1
      done
      if kill -0 "$pid" 2>/dev/null && [ "$(awk '{print $3}' "/proc/$pid/stat" 2>/dev/null || true)" != Z ]; then
        echo '[nextcloud-office] Cannot reset while the old office server is still running.' >&2
        return 1
      fi
    fi
  fi
}

configure_runtime_url() {
  local public_url trusted_domains

  public_url="$(nextcloud_public_url)"
  trusted_domains="${NEXTCLOUD_TRUSTED_DOMAINS:-localhost 127.0.0.1}"

  php -r '
    $configPath = $argv[1];
    $publicUrl = rtrim($argv[2], "/");
    $trustedRaw = $argv[3];
    $CONFIG = [];
    include $configPath;

    $domains = preg_split("/\s+/", trim($trustedRaw)) ?: [];
    $host = parse_url($publicUrl, PHP_URL_HOST);
    $port = parse_url($publicUrl, PHP_URL_PORT);
    if ($host) {
      $domains[] = $host;
      if ($port) {
        $domains[] = $host . ":" . $port;
      }
    }

    $seen = [];
    $trusted = [];
    foreach ($domains as $domain) {
      if ($domain === "" || isset($seen[$domain])) {
        continue;
      }
      $seen[$domain] = true;
      $trusted[] = $domain;
    }

    $CONFIG["overwrite.cli.url"] = $publicUrl;
    $CONFIG["trusted_domains"] = $trusted;
    if (file_put_contents(
      $configPath,
      "<?php\n\$CONFIG = " . var_export($CONFIG, true) . ";\n"
    ) === false) {
      fwrite(STDERR, "Unable to write Nextcloud runtime configuration\n");
      exit(1);
    }
  ' "$HTML_DIR/config/config.php" "$public_url" "$trusted_domains"

  configure_office_loopback
  configure_richdocuments_url "$public_url"
}

repair_runtime_state() {
  # Tree snapshots and legacy tarballs can carry root-owned config/data. Repair
  # them before running occ as the same user that serves HTTP requests.
  chown -R www-data:www-data "$HTML_DIR/config" "$HTML_DIR/data"
  configure_runtime_url

  # A clean volume starts with the distribution .htaccess, which lacks the
  # post-install rewrite block. Restore the template if it was deleted, then
  # regenerate after setting the runtime URL rather than preserving seed URLs.
  if [ ! -f "$HTML_DIR/.htaccess" ]; then
    cp /usr/src/nextcloud/.htaccess "$HTML_DIR/.htaccess"
  fi
  chown www-data:www-data "$HTML_DIR/.htaccess"
  if ! su -s /bin/sh www-data -c 'cd /var/www/html && php occ maintenance:update:htaccess'; then
    echo "[nextcloud-runtime] Failed to regenerate /var/www/html/.htaccess as www-data; check runtime URL, config/data ownership, write permissions and free space. Login readiness cannot succeed until this is fixed." >&2
    return 1
  fi
}

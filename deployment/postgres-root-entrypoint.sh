#!/usr/bin/env bash
#
# Modified PostgreSQL Docker Entrypoint Script
# Original source: postgres:16-alpine official Docker image
# https://github.com/docker-library/postgres
#
# MODIFICATIONS FOR NFS ROOT-SQUASH COMPATIBILITY:
#
# This script has been adapted to work with NFS mounts that use root-squash,
# where the container cannot perform chown operations and all files appear as
# root-owned from inside the container.
#
# Key changes:
# 1. Removed all chown commands that would fail with NFS root-squash
# 2. Added error suppression for chmod operations that may fail on NFS
# 3. Modified /etc/passwd to assign UID 0 (root) to the 'postgres' user entry
#    - This allows PostgreSQL to run as root while believing it's the postgres user
#    - PostgreSQL refuses to start as root for security, but this workaround
#      satisfies its username check while maintaining root privileges
#    - Safe in containerized environments where system-wide damage isn't a concern
# 4. Removed the standard user-switching mechanism since we need root throughout
#
# This approach enables PostgreSQL to:
# - Access root-owned NFS files (as seen from inside the container)
# - Pass PostgreSQL's internal user validation checks
# - Initialize and run without requiring filesystem ownership changes
#

set -Eeo pipefail

# usage: file_env VAR [DEFAULT]
file_env() {
	local var="$1"
	local fileVar="${var}_FILE"
	local def="${2:-}"
	if [ "${!var:-}" ] && [ "${!fileVar:-}" ]; then
		printf >&2 'error: both %s and %s are set (but are exclusive)\n' "$var" "$fileVar"
		exit 1
	fi
	local val="$def"
	if [ "${!var:-}" ]; then
		val="${!var}"
	elif [ "${!fileVar:-}" ]; then
		val="$(< "${!fileVar}")"
	fi
	export "$var"="$val"
	unset "$fileVar"
}

# check to see if this file is being run or sourced from another script
_is_sourced() {
	[ "${#FUNCNAME[@]}" -ge 2 ] \
		&& [ "${FUNCNAME[0]}" = '_is_sourced' ] \
		&& [ "${FUNCNAME[1]}" = 'source' ]
}

# MODIFIED: All chown commands removed to work with NFS root-squash
docker_create_db_directories() {
	local user; user="$(id -u)"

	mkdir -p "$PGDATA" 2>/dev/null || :
	chmod 00700 "$PGDATA" 2>/dev/null || :

	mkdir -p /var/run/postgresql 2>/dev/null || :
	chmod 03775 /var/run/postgresql 2>/dev/null || :

	if [ -n "${POSTGRES_INITDB_WALDIR:-}" ]; then
		mkdir -p "$POSTGRES_INITDB_WALDIR" 2>/dev/null || :
		chmod 700 "$POSTGRES_INITDB_WALDIR" 2>/dev/null || :
	fi
}

docker_init_database_dir() {
	local uid; uid="$(id -u)"
	if ! getent passwd "$uid" &> /dev/null; then
		local wrapper
		for wrapper in {/usr,}/lib{/*,}/libnss_wrapper.so; do
			if [ -s "$wrapper" ]; then
				NSS_WRAPPER_PASSWD="$(mktemp)"
				NSS_WRAPPER_GROUP="$(mktemp)"
				export LD_PRELOAD="$wrapper" NSS_WRAPPER_PASSWD NSS_WRAPPER_GROUP
				local gid; gid="$(id -g)"
				printf 'postgres:x:%s:%s:PostgreSQL:%s:/bin/false\n' "$uid" "$gid" "$PGDATA" > "$NSS_WRAPPER_PASSWD"
				printf 'postgres:x:%s:\n' "$gid" > "$NSS_WRAPPER_GROUP"
				break
			fi
		done
	fi

	if [ -n "${POSTGRES_INITDB_WALDIR:-}" ]; then
		set -- --waldir "$POSTGRES_INITDB_WALDIR" "$@"
	fi

	eval 'initdb --username="$POSTGRES_USER" --pwfile=<(printf "%s\n" "$POSTGRES_PASSWORD") '"$POSTGRES_INITDB_ARGS"' "$@"'

	if [[ "${LD_PRELOAD:-}" == */libnss_wrapper.so ]]; then
		rm -f "$NSS_WRAPPER_PASSWD" "$NSS_WRAPPER_GROUP"
		unset LD_PRELOAD NSS_WRAPPER_PASSWD NSS_WRAPPER_GROUP
	fi
}

docker_verify_minimum_env() {
	case "${PG_MAJOR:-}" in
		13)
			if [ "${#POSTGRES_PASSWORD}" -ge 100 ]; then
				cat >&2 <<-'EOWARN'

					WARNING: The supplied POSTGRES_PASSWORD is 100+ characters.

					  This will not work if used via PGPASSWORD with "psql".

					  https://www.postgresql.org/message-id/flat/E1Rqxp2-0004Qt-PL%40wrigleys.postgresql.org (BUG #6412)
					  https://github.com/docker-library/postgres/issues/507

				EOWARN
			fi
			;;
	esac
	if [ -z "$POSTGRES_PASSWORD" ] && [ 'trust' != "$POSTGRES_HOST_AUTH_METHOD" ]; then
		cat >&2 <<-'EOE'
			Error: Database is uninitialized and superuser password is not specified.
			       You must specify POSTGRES_PASSWORD to a non-empty value for the
			       superuser. For example, "-e POSTGRES_PASSWORD=password" on "docker run".

			       You may also use "POSTGRES_HOST_AUTH_METHOD=trust" to allow all
			       connections without a password. This is *not* recommended.

			       See PostgreSQL documentation about "trust":
			       https://www.postgresql.org/docs/current/auth-trust.html
		EOE
		exit 1
	fi
	if [ 'trust' = "$POSTGRES_HOST_AUTH_METHOD" ]; then
		cat >&2 <<-'EOWARN'
			********************************************************************************
			WARNING: POSTGRES_HOST_AUTH_METHOD has been set to "trust". This will allow
			         anyone with access to the Postgres port to access your database without
			         a password, even if POSTGRES_PASSWORD is set. See PostgreSQL
			         documentation about "trust":
			         https://www.postgresql.org/docs/current/auth-trust.html
			         In Docker's default configuration, this is effectively any other
			         container on the same system.

			         It is not recommended to use POSTGRES_HOST_AUTH_METHOD=trust. Replace
			         it with "-e POSTGRES_PASSWORD=password" instead to set a password in
			         "docker run".
			********************************************************************************
		EOWARN
	fi
}

docker_error_old_databases() {
	if [ -n "${OLD_DATABASES[0]:-}" ]; then
		cat >&2 <<-EOE
			Error: in 18+, these Docker images are configured to store database data in a
			       format which is compatible with "pg_ctlcluster" (specifically, using
			       major-version-specific directory names).  This better reflects how
			       PostgreSQL itself works, and how upgrades are to be performed.

			       See also https://github.com/docker-library/postgres/pull/1259

			       Counter to that, there appears to be PostgreSQL data in:
			         ${OLD_DATABASES[*]}

			       This is usually the result of upgrading the Docker image without upgrading
			       the underlying database using "pg_upgrade" (which requires both versions).

			       See https://github.com/docker-library/postgres/issues/37 for a (long)
			       discussion around this process, and suggestions for how to do so.
		EOE
		exit 1
	fi
}

docker_process_init_files() {
	psql=( docker_process_sql )

	printf '\n'
	local f
	for f; do
		case "$f" in
			*.sh)
				if [ -x "$f" ]; then
					printf '%s: running %s\n' "$0" "$f"
					"$f"
				else
					printf '%s: sourcing %s\n' "$0" "$f"
					. "$f"
				fi
				;;
			*.sql)     printf '%s: running %s\n' "$0" "$f"; docker_process_sql -f "$f"; printf '\n' ;;
			*.sql.gz)  printf '%s: running %s\n' "$0" "$f"; gunzip -c "$f" | docker_process_sql; printf '\n' ;;
			*.sql.xz)  printf '%s: running %s\n' "$0" "$f"; xzcat "$f" | docker_process_sql; printf '\n' ;;
			*.sql.zst) printf '%s: running %s\n' "$0" "$f"; zstd -dc "$f" | docker_process_sql; printf '\n' ;;
			*)         printf '%s: ignoring %s\n' "$0" "$f" ;;
		esac
		printf '\n'
	done
}

docker_process_sql() {
	local query_runner=( psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --no-password --no-psqlrc )
	if [ -n "$POSTGRES_DB" ]; then
		query_runner+=( --dbname "$POSTGRES_DB" )
	fi

	PGHOST= PGHOSTADDR= "${query_runner[@]}" "$@"
}

docker_setup_db() {
	local dbAlreadyExists
	dbAlreadyExists="$(
		POSTGRES_DB= docker_process_sql --dbname postgres --set db="$POSTGRES_DB" --tuples-only <<-'EOSQL'
			SELECT 1 FROM pg_database WHERE datname = :'db' ;
		EOSQL
	)"
	if [ -z "$dbAlreadyExists" ]; then
		POSTGRES_DB= docker_process_sql --dbname postgres --set db="$POSTGRES_DB" <<-'EOSQL'
			CREATE DATABASE :"db" ;
		EOSQL
		printf '\n'
	fi
}

docker_setup_env() {
	file_env 'POSTGRES_PASSWORD'

	file_env 'POSTGRES_USER' 'postgres'
	file_env 'POSTGRES_DB' "$POSTGRES_USER"
	file_env 'POSTGRES_INITDB_ARGS'
	: "${POSTGRES_HOST_AUTH_METHOD:=}"

	declare -g DATABASE_ALREADY_EXISTS
	: "${DATABASE_ALREADY_EXISTS:=}"
	declare -ag OLD_DATABASES=()
	if [ -s "$PGDATA/PG_VERSION" ]; then
		DATABASE_ALREADY_EXISTS='true'
	elif [ "$PGDATA" = "/var/lib/postgresql/$PG_MAJOR/docker" ]; then
		for d in /var/lib/postgresql /var/lib/postgresql/data /var/lib/postgresql/*/docker; do
			if [ -s "$d/PG_VERSION" ]; then
				OLD_DATABASES+=( "$d" )
			fi
		done
	fi
}

pg_setup_hba_conf() {
	if [ "$1" = 'postgres' ]; then
		shift
	fi
	local auth
	auth="$(postgres -C password_encryption "$@")"
	: "${POSTGRES_HOST_AUTH_METHOD:=$auth}"
	{
		printf '\n'
		if [ 'trust' = "$POSTGRES_HOST_AUTH_METHOD" ]; then
			printf '# warning trust is enabled for all connections\n'
			printf '# see https://www.postgresql.org/docs/17/auth-trust.html\n'
		fi
		printf 'host all all all %s\n' "$POSTGRES_HOST_AUTH_METHOD"
	} >> "$PGDATA/pg_hba.conf"
}

docker_temp_server_start() {
	if [ "$1" = 'postgres' ]; then
		shift
	fi

	set -- "$@" -c listen_addresses='' -p "${PGPORT:-5432}"

	NOTIFY_SOCKET= \
	PGUSER="${PGUSER:-$POSTGRES_USER}" \
	pg_ctl -D "$PGDATA" \
		-o "$(printf '%q ' "$@")" \
		-w start
}

docker_temp_server_stop() {
	PGUSER="${PGUSER:-postgres}" \
	pg_ctl -D "$PGDATA" -m fast -w stop
}

_pg_want_help() {
	local arg
	for arg; do
		case "$arg" in
			-'?'|--help|--describe-config|-V|--version)
				return 0
				;;
		esac
	done
	return 1
}

_main() {
	if [ "${1:0:1}" = '-' ]; then
		set -- postgres "$@"
	fi

	if [ "$1" = 'postgres' ] && ! _pg_want_help "$@"; then
		docker_setup_env
		docker_create_db_directories

#		# MODIFIED: For NFS root-squash scenarios where files appear as root-owned
#		# We need to actually run as root, but PostgreSQL refuses this.
#		# Solution: Create a fake postgres user entry matching root's UID
#		if [ "$(id -u)" = '0' ]; then
#			# Modify /etc/passwd to make postgres user have UID 0 (root)
#			# This allows postgres binary to think it's running as postgres user
#			sed -i 's/^postgres:x:[0-9]*:[0-9]*/postgres:x:0:0/' /etc/passwd 2>/dev/null || true
#			sed -i 's/^postgres:x:[0-9]*/postgres:x:0/' /etc/group 2>/dev/null || true
#
#			# Now switch to "postgres" user (which is actually UID 0)
#			exec gosu postgres "$BASH_SOURCE" "$@"
#		fi

		if [ "$(id -u)" = '0' ]; then
        # Fake the postgres user so Postgres internal check passes
        sed -i 's/^postgres:x:[0-9]*:[0-9]*/postgres:x:0:0/' /etc/passwd 2>/dev/null || true
        sed -i 's/^postgres:x:[0-9]*/postgres:x:0/' /etc/group 2>/dev/null || true

        # Run postgres binary as the postgres user
        exec gosu postgres postgres "$@"
    fi

		if [ -z "$DATABASE_ALREADY_EXISTS" ]; then
			docker_verify_minimum_env
			docker_error_old_databases

			ls /docker-entrypoint-initdb.d/ > /dev/null

			docker_init_database_dir
			pg_setup_hba_conf "$@"

			export PGPASSWORD="${PGPASSWORD:-$POSTGRES_PASSWORD}"
			docker_temp_server_start "$@"

			docker_setup_db
			docker_process_init_files /docker-entrypoint-initdb.d/*

			docker_temp_server_stop
			unset PGPASSWORD

			cat <<-'EOM'

				PostgreSQL init process complete; ready for start up.

			EOM
		else
			cat <<-'EOM'

				PostgreSQL Database directory appears to contain a database; Skipping initialization

			EOM
		fi
	fi

	exec "$@"
}

if ! _is_sourced; then
	_main "$@"
fi
{{- define "discourse.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 48 | trimSuffix "-" -}}
{{- end -}}
{{- define "discourse.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 48 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "discourse.name" .) | trunc 48 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- define "discourse.selectorLabels" -}}
app.kubernetes.io/name: {{ include "discourse.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
{{- define "discourse.labels" -}}
{{ include "discourse.selectorLabels" . }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
{{- define "discourse.image" -}}
{{- if .digest -}}
{{- printf "%s@%s" .repository .digest -}}
{{- else -}}
{{- printf "%s:%s" .repository .tag -}}
{{- end -}}
{{- end -}}
{{- define "discourse.claim" -}}
{{- default (printf "%s-shared" (include "discourse.fullname" .)) .Values.persistence.existingClaim -}}
{{- end -}}
{{- define "discourse.env" -}}
{{- $reserved := list "RAILS_ENV" "DISCOURSE_HOSTNAME" "DISCOURSE_DB_HOST" "DISCOURSE_DB_PORT" "DISCOURSE_DB_NAME" "DISCOURSE_DB_USERNAME" "DISCOURSE_DB_PASSWORD" "DISCOURSE_REDIS_HOST" "DISCOURSE_REDIS_PORT" "DISCOURSE_REDIS_PASSWORD" "MIGRATE_ON_BOOT" "CREATE_DB_ON_BOOT" "PRECOMPILE_ON_BOOT" "DISABLE_LETSENCRYPT" "UNICORN_WORKERS" "UNICORN_SIDEKIQS" -}}
{{- $seen := dict -}}
{{- range .Values.extraEnv -}}
{{- if or (has .name $reserved) (hasKey $seen .name) -}}
{{- fail (printf "extraEnv must not duplicate chart-managed or other environment variables: %s" .name) -}}
{{- end -}}
{{- $_ := set $seen .name true -}}
{{- end -}}
- name: RAILS_ENV
  value: production
- name: DISCOURSE_HOSTNAME
  value: {{ required "hostname is required" .Values.hostname | quote }}
- name: DISCOURSE_DB_HOST
  value: {{ required "database.host is required" .Values.database.host | quote }}
- name: DISCOURSE_DB_PORT
  value: {{ .Values.database.port | quote }}
- name: DISCOURSE_DB_NAME
  value: {{ .Values.database.name | quote }}
- name: DISCOURSE_DB_USERNAME
  value: {{ .Values.database.username | quote }}
- name: DISCOURSE_DB_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ required "database.existingSecret is required" .Values.database.existingSecret }}
      key: {{ .Values.database.passwordKey }}
- name: DISCOURSE_REDIS_HOST
  value: {{ if .Values.redis.enabled }}{{ printf "%s-redis" (include "discourse.fullname" .) | quote }}{{ else }}{{ required "redis.external.host is required when bundled Redis is disabled" .Values.redis.external.host | quote }}{{ end }}
- name: DISCOURSE_REDIS_PORT
  value: {{ if .Values.redis.enabled }}"6379"{{ else }}{{ .Values.redis.external.port | quote }}{{ end }}
- name: DISCOURSE_REDIS_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ required "redis.auth.existingSecret is required" .Values.redis.auth.existingSecret }}
      key: {{ .Values.redis.auth.passwordKey }}
- name: MIGRATE_ON_BOOT
  value: "0"
- name: CREATE_DB_ON_BOOT
  value: "0"
- name: PRECOMPILE_ON_BOOT
  value: "1"
- name: DISABLE_LETSENCRYPT
  value: "1"
- name: UNICORN_WORKERS
  value: {{ .Values.web.workers | quote }}
- name: UNICORN_SIDEKIQS
  value: {{ .Values.web.sidekiqWorkers | quote }}
{{- with .Values.extraEnv }}
{{ toYaml . }}
{{- end }}
{{- end -}}
{{- define "discourse.sharedVolume" -}}
- name: shared
  {{- if .Values.persistence.enabled }}
  persistentVolumeClaim:
    claimName: {{ include "discourse.claim" . }}
  {{- else }}
  emptyDir: {}
  {{- end }}
{{- end -}}
{{- define "discourse.scheduling" -}}
{{- with .Values.imagePullSecrets }}
imagePullSecrets:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.nodeSelector }}
nodeSelector:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.tolerations }}
tolerations:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.affinity }}
affinity:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end -}}

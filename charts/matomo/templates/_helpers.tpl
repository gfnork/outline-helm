{{- define "matomo.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 48 | trimSuffix "-" -}}
{{- end -}}
{{- define "matomo.fullname" -}}
{{- default (printf "%s-%s" .Release.Name (include "matomo.name" .)) .Values.fullnameOverride | trunc 48 | trimSuffix "-" -}}
{{- end -}}
{{- define "matomo.selectorLabels" -}}
app.kubernetes.io/name: {{ include "matomo.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
{{- define "matomo.labels" -}}
{{ include "matomo.selectorLabels" . }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | quote }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
{{- define "matomo.image" -}}
{{- if .digest -}}{{ printf "%s@%s" .repository .digest }}{{- else -}}{{ printf "%s:%s" .repository .tag }}{{- end -}}
{{- end -}}
{{- define "matomo.claim" -}}
{{- default (printf "%s-data" (include "matomo.fullname" .)) .Values.persistence.existingClaim -}}
{{- end -}}
{{- define "matomo.databaseHost" -}}
{{- if .Values.mariadb.enabled -}}{{ include "matomo.fullname" . }}-mariadb{{- else -}}{{ required "database.host is required" .Values.database.host }}{{- end -}}
{{- end -}}
{{- define "matomo.env" -}}
{{- $reserved := list "MATOMO_DATABASE_HOST" "MATOMO_DATABASE_USERNAME" "MATOMO_DATABASE_PASSWORD" "MATOMO_DATABASE_DBNAME" "PHP_MEMORY_LIMIT" -}}
{{- $seen := dict -}}
{{- range .Values.extraEnv -}}
{{- if or (has .name $reserved) (hasKey $seen .name) -}}{{ fail (printf "extraEnv duplicates a managed or existing variable: %s" .name) }}{{- end -}}
{{- $_ := set $seen .name true -}}
{{- end -}}
- name: MATOMO_DATABASE_HOST
  value: {{ printf "%s:%v" (include "matomo.databaseHost" .) .Values.database.port | quote }}
- name: MATOMO_DATABASE_USERNAME
  value: {{ .Values.database.username | quote }}
- name: MATOMO_DATABASE_DBNAME
  value: {{ .Values.database.name | quote }}
- name: MATOMO_DATABASE_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ required "database.existingSecret is required" .Values.database.existingSecret }}
      key: {{ .Values.database.passwordKey }}
- name: PHP_MEMORY_LIMIT
  value: {{ .Values.php.memoryLimit | quote }}
{{- with .Values.extraEnv }}
{{ toYaml . }}
{{- end }}
{{- end -}}
{{- define "matomo.mounts" -}}
- {name: application, mountPath: /var/www/html}
- {name: data, mountPath: /var/www/html/config, subPath: config}
- {name: data, mountPath: /var/www/html/plugins, subPath: plugins}
- {name: data, mountPath: /var/www/html/tmp, subPath: tmp}
- {name: data, mountPath: /var/www/html/js, subPath: js}
- {name: data, mountPath: /var/www/html/misc, subPath: misc}
- {name: runtime, mountPath: /tmp, subPath: tmp}
- {name: runtime, mountPath: /var/run/apache2, subPath: apache-run}
- {name: runtime, mountPath: /var/lock/apache2, subPath: apache-lock}
- {name: settings, mountPath: /usr/local/etc/php/conf.d/zz-chart.ini, subPath: php.ini, readOnly: true}
{{- end -}}
{{- define "matomo.volumes" -}}
- name: application
  emptyDir: {}
- name: data
  {{- if .Values.persistence.enabled }}
  persistentVolumeClaim:
    claimName: {{ include "matomo.claim" . }}
  {{- else }}
  emptyDir: {}
  {{- end }}
- name: runtime
  emptyDir: {}
- name: settings
  configMap:
    name: {{ include "matomo.fullname" . }}-php
{{- if .Values.config.existingSecret }}
- name: seed-config
  secret:
    secretName: {{ .Values.config.existingSecret }}
    items:
      - {key: {{ .Values.config.key | quote }}, path: config.ini.php}
{{- end }}
{{- end -}}
{{- define "matomo.init" -}}
{{- $root := .root -}}
- name: prepare-application
  image: {{ include "matomo.image" $root.Values.image | quote }}
  imagePullPolicy: {{ $root.Values.image.pullPolicy }}
  securityContext:
    runAsUser: 0
    runAsGroup: 0
    allowPrivilegeEscalation: false
    readOnlyRootFilesystem: true
    capabilities:
      drop: [ALL]
      add: [CHOWN, DAC_OVERRIDE, FOWNER]
    seccompProfile: {type: RuntimeDefault}
  command: [/bin/sh, -ec]
  args:
    - |
      mkdir -p /runtime/tmp /runtime/apache-run /runtime/apache-lock
      chmod 1777 /runtime/tmp
      chown 33:33 /runtime/apache-run /runtime/apache-lock
      cp -a /usr/src/matomo/. /application/
      mkdir -p /data/config /data/plugins /data/tmp /data/misc /data/js
      {{- if .initializeData }}
      cp /usr/src/matomo/config/global.ini.php /data/config/global.ini.php
      cp -a /usr/src/matomo/js/. /data/js/
      cp -a /usr/src/matomo/misc/. /data/misc/
      for plugin in /usr/src/matomo/plugins/*; do
        name="${plugin##*/}"
        rm -rf "/data/plugins/$name"
        cp -a "$plugin" "/data/plugins/$name"
      done
      {{- if $root.Values.config.existingSecret }}
      if [ ! -f /data/config/config.ini.php ]; then
        cp /seed/config.ini.php /data/config/config.ini.php
      fi
      {{- end }}
      chown -R 33:33 /data/config /data/plugins /data/tmp /data/misc /data/js
      {{- end }}
      chown -R 33:33 /application
  resources:
    requests: {cpu: 100m, memory: 128Mi}
    limits: {memory: 512Mi}
  volumeMounts:
    - {name: application, mountPath: /application}
    - {name: runtime, mountPath: /runtime}
    - {name: data, mountPath: /data}
    {{- if $root.Values.config.existingSecret }}
    - {name: seed-config, mountPath: /seed, readOnly: true}
    {{- end }}
{{- end -}}
{{- define "matomo.scheduling" -}}
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

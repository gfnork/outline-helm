{{- define "roadatlas.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "roadatlas.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "roadatlas.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{ include "roadatlas.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "roadatlas.selectorLabels" -}}
app.kubernetes.io/name: {{ include "roadatlas.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "roadatlas.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "roadatlas.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "roadatlas.image" -}}
{{- if .digest -}}
{{- printf "%s@%s" .repository .digest -}}
{{- else -}}
{{- printf "%s:%s" .repository .tag -}}
{{- end -}}
{{- end -}}

{{- define "roadatlas.postgresqlName" -}}
{{- printf "%s-postgresql" (include "roadatlas.fullname" .) -}}
{{- end -}}

{{- define "roadatlas.appEnv" -}}
- name: BETTER_AUTH_URL
  value: {{ .Values.config.betterAuthUrl | quote }}
- name: PHOTON_API_URL
  value: {{ .Values.config.photonApiUrl | quote }}
- name: OSRM_API_URL
  value: {{ .Values.config.osrmApiUrl | quote }}
- name: TRIP_ALGORITHM
  value: {{ .Values.config.tripAlgorithm | quote }}
- name: LOCAL_GEOCODER_MAX_DISTANCE_KM
  value: {{ .Values.config.localGeocoderMaxDistanceKm | quote }}
- name: PLACE_INDEX_LOCAL_DIR
  value: /var/lib/roadatlas/place-index
- name: GEONAMES_DATA_DIR
  value: /var/lib/roadatlas/geonames
- name: PLACE_INDEX_BASE_URL
  value: ""
{{- end -}}


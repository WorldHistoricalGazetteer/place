local kp =
  (import 'kube-prometheus/jsonnet/kube-prometheus/main.libsonnet') +
  {
    values+:: {
      common+: {
        namespace: 'monitoring',
      },
    },

    prometheus+:: {
      prometheus+: {
        spec+: {
          retention: '30d',

          storage: {
            volumes: [
              {
                name: prometheus-storage,
                persistentVolumeClaim: {
                  claimName: 'prometheus-pvc',
                },
              },
            ],
            volumeMounts: [
              {
                name: prometheus-storage,
                mountPath: '/prometheus',
              },
            ],
          },
        },
      },
    },

    grafana+:: {
      grafana+: {
        spec+: {
          volumes: [
            {
              name: grafana-storage,
              persistentVolumeClaim: {
                claimName: 'grafana-pvc',
              },
            },
          ],
          volumeMounts: [
            {
              name: grafana-storage,
              mountPath: '/var/lib/grafana',
            },
          ],
        },
      },
    },
  };

{ ['setup/0namespace-' + name]: kp.kubePrometheus[name] for name in std.objectFields(kp.kubePrometheus) } +
{
  ['setup/prometheus-operator-' + name]: kp.prometheusOperator[name]
  for name in std.filter((function(name) name != 'serviceMonitor'), std.objectFields(kp.prometheusOperator))
} +
{ 'prometheus-operator-serviceMonitor': kp.prometheusOperator.serviceMonitor } +
{ ['node-exporter-' + name]: kp.nodeExporter[name] for name in std.objectFields(kp.nodeExporter) } +
{ ['kube-state-metrics-' + name]: kp.kubeStateMetrics[name] for name in std.objectFields(kp.kubeStateMetrics) } +
{ ['alertmanager-' + name]: kp.alertmanager[name] for name in std.objectFields(kp.alertmanager) } +
{ ['prometheus-' + name]: kp.prometheus[name] for name in std.objectFields(kp.prometheus) } +
{ ['prometheus-adapter-' + name]: kp.prometheusAdapter[name] for name in std.objectFields(kp.prometheusAdapter) } +
{ ['grafana-' + name]: kp.grafana[name] for name in std.objectFields(kp.grafana) }
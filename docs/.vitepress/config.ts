import { withMermaid } from 'vitepress-plugin-mermaid'

export default withMermaid({
  title: 'Geo Activity Playground',
  description: 'View recorded outdoor activities and derive insights from your data.',
  base: '/geo-activity-playground/',
  themeConfig: {
    logo: '/logo-2.png',
    nav: [
      { text: 'Docs', link: '/getting-started' },
      { text: 'Changelog', link: '/changelog' },
      { text: 'Get Help', link: '/get-help' },
      { text: "Martin Ueding", link: "https://martin-ueding.de/" },
    ],
    sidebar: [
      { text: 'Home', link: '/' },
      {
        text: 'Overview',
        items: [
          { text: 'Getting Started', link: '/getting-started' },
          { text: 'Screenshot Tour', link: '/screenshot-tour' },
          { text: 'Similar Projects', link: '/similar-projects' },
        ],
      },
      {
        text: 'Installation',
        items: [
          { text: 'Install on Linux', link: '/install-on-linux' },
          { text: 'Install on Windows', link: '/install-on-windows' },
          { text: 'Install on macOS', link: '/install-on-macos' },
          { text: 'Add Local Bin to PATH', link: '/add-local-bin-to-path' },
          { text: 'Create a Base Directory', link: '/create-a-base-directory' },
          { text: 'Starting the Program', link: '/starting-the-webserver' },
        ],
      },
      {
        text: 'Docker Installation',
        items: [
          { text: 'Start with Docker Run', link: '/docker-run' },
          { text: 'Using Docker Compose', link: '/using-docker-compose' },
          { text: 'Docker Compose + Tailscale VPN', link: '/using-docker-compose-and-tailscale-vpn' },
        ],
      },
      {
        text: 'Importing Activities',
        items: [
          { text: 'Choosing an Activity Source', link: '/activity-sources' },
          { text: 'Import Activity Files', link: '/import-activity-files' },
          { text: 'Upload Activity Files', link: '/upload-activity-files' },
          { text: 'Connect Strava API', link: '/connect-strava-api' },
          { text: 'Moving from Strava', link: '/moving-from-strava' },
          { text: 'Record Activities', link: '/record-activities' },
          { text: 'Rename Activity Kinds', link: '/rename-activity-kinds' },
          { text: 'Advanced Metadata Extraction', link: '/advanced-metadata-extraction' },
          { text: 'Sync Between Computers', link: '/sync-between-computers' },
        ],
      },
      {
        text: 'Explorer Tiles',
        items: [
          { text: 'Explorer Tiles', link: '/explorer-tiles' },
          { text: 'Plan Missing Tile Rides', link: '/plan-missing-tile-rides' },
          { text: 'Explorer Tiles on the Go', link: '/explorer-tiles-on-the-go' },
          { text: 'Cluster History', link: '/cluster-history' },
          { text: 'Incremental Cluster Algorithm', link: '/incremental-cluster-algorithm' },
        ],
      },
      {
        text: 'Maps & Plots',
        items: [
          { text: 'Using Maps as Overlays', link: '/using-maps-as-overlays' },
          { text: 'Build Custom Plots', link: '/build-custom-plots' },
          { text: 'Create a Privacy Zone', link: '/create-a-privacy-zone' },
        ],
      },
      {
        text: 'Metrics',
        items: [
          { text: 'Eddington Number', link: '/eddington-number' },
          { text: 'Heart Rate Zones', link: '/heart-rate-zones' },
          { text: 'Elevation Gain from Noisy Data', link: '/elevation-gain-from-noisy-data' },
          { text: "Satellite Elevation Isn't Helpful", link: '/satellite-elevation-isnt-helpful' },
          { text: 'Segment Matching', link: '/segment-matching' },
          { text: 'Time Zone Handling Sucks', link: '/time-zone-handling-sucks' },
        ],
      },
      { text: 'Bike Maintenance Tracker', link: '/bike-maintenance-tracker' },
      {
        text: 'Contributing',
        items: [
          { text: 'Set Up a Development Environment', link: '/set-up-a-development-environment' },
          { text: 'Change Database Schema', link: '/change-database-schema' },
          { text: 'Update and Extend Translations', link: '/update-and-extend-translations' },
        ],
      },
      {
        text: 'About',
        items: [
          { text: 'Contributors', link: '/contributors' },
          { text: 'Acknowledgments', link: '/acknowledgments' },
          { text: 'License', link: '/license' },
          { text: 'Get Help', link: '/get-help' },
          { text: 'Changelog', link: '/changelog' },
        ],
      },
    ],
    socialLinks: [
      { icon: 'github', link: 'https://github.com/martin-ueding/geo-activity-playground' },
      { icon: 'python', link: 'https://pypi.org/project/geo-activity-playground/' },
      { icon: 'mastodon', link: 'https://bonn.social/tags/GeoActivityPlayground' },
      { icon: 'email', link: 'mailto:mu@martin-ueding.de' },
    ],
    outline: {
      level: [2, 3],
    },
    search: {
      provider: 'local',
    },
  },
})

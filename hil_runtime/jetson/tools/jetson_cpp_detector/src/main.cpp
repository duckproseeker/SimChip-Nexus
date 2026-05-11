#include <trt_yolo.hpp>

#include <algorithm>
#include <atomic>
#include <cctype>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <cstdlib>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace
{
using Clock = std::chrono::steady_clock;
std::atomic_bool g_shutdown_requested{false};

void request_shutdown(int)
{
  g_shutdown_requested.store(true);
}

struct Options
{
  std::string source = "udp://0.0.0.0:5000";
  std::string decoder = "nvv4l2decoder";
  std::string engine_path = "~/yolo_ros2/module/yolov4-tiny.engine";
  std::string label_path = "~/yolo_ros2/module/coco.names";
  std::string metrics_file;
  std::string latency_samples_file;
  std::string window_name = "DuckPark C++ Detector";
  float ignore_thresh = 0.5F;
  int gpu_id = 0;
  int max_frames = 0;
  bool display = false;
  bool loop_file = false;
  bool swap_rb = false;
  bool verbose = false;
};

struct Metrics
{
  std::uint64_t processed_frames = 0;
  std::uint64_t detection_count = 0;
  std::uint64_t last_detection_count = 0;
  double avg_latency_ms = 0.0;
  double latency_max_ms = 0.0;
  double latency_p50_ms = 0.0;
  double latency_p95_ms = 0.0;
  double latency_p99_ms = 0.0;
  double output_fps = 0.0;
  int frame_width = 0;
  int frame_height = 0;
  int model_channels = 0;
  int model_height = 0;
  int model_width = 0;
  int max_detections = 0;
  bool display_enabled = false;
  bool swap_rb = false;
  bool latency_distribution_ready = false;
  std::string source;
  std::string decoder;
  std::string engine_path;
  std::string started_at_utc;
  std::string ended_at_utc;
  std::string timestamp_utc;
};

void print_usage(const char * argv0)
{
  std::cout
    << "Usage:\n"
    << "  " << argv0 << " [options]\n\n"
    << "Options:\n"
    << "  --source <uri>         Input source. Default udp://0.0.0.0:5000\n"
    << "  --decoder <name>       RTP hardware decoder. Default nvv4l2decoder\n"
    << "  --engine <path>        TensorRT engine path\n"
    << "  --labels <path>        Label file path\n"
    << "  --metrics-file <path>  Write running metrics JSON to this file\n"
    << "  --latency-samples-file <path>\n"
    << "                         Write final per-frame latency samples CSV to this file\n"
    << "  --ignore-thresh <f>    Display threshold. Default 0.5\n"
    << "  --gpu-id <n>           CUDA device id. Default 0\n"
    << "  --display              Enable cv::imshow output\n"
    << "  --no-display           Disable cv::imshow output\n"
    << "  --window-name <text>   OpenCV window title\n"
    << "  --max-frames <n>       Exit after N frames. Default 0 means unlimited\n"
    << "  --loop-file            Reopen file inputs at EOF\n"
    << "  --swap-rb              Swap red and blue channels before inference/display\n"
    << "  --verbose              Print extra logs\n"
    << "  --help                 Show this help\n\n"
    << "Notes:\n"
    << "  - RTP sources use a GStreamer pipeline with rtph264depay + h264parse + decoder.\n"
    << "  - File inputs are opened directly through OpenCV.\n";
}

std::string now_utc_iso8601()
{
  const auto now = std::chrono::system_clock::now();
  const auto now_time_t = std::chrono::system_clock::to_time_t(now);
  std::tm tm{};
#if defined(_WIN32)
  gmtime_s(&tm, &now_time_t);
#else
  gmtime_r(&now_time_t, &tm);
#endif
  char buffer[32];
  std::strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", &tm);
  return buffer;
}

void log_message(const std::string & message)
{
  std::cout << now_utc_iso8601() << " duckpark-cpp-detector " << message << std::endl;
}

bool starts_with(const std::string & value, const std::string & prefix)
{
  return value.rfind(prefix, 0) == 0;
}

bool is_number(const std::string & value)
{
  return !value.empty() && std::all_of(value.begin(), value.end(), [](unsigned char ch) {
           return std::isdigit(ch) != 0;
         });
}

std::string expand_user(std::string path)
{
  if (path.empty() || path[0] != '~') {
    return path;
  }
  const char * home = std::getenv("HOME");
  if (home == nullptr || *home == '\0') {
    return path;
  }
  if (path.size() == 1) {
    return std::string(home);
  }
  if (path[1] == '/') {
    return std::string(home) + path.substr(1);
  }
  return path;
}

std::vector<std::string> load_labels(const std::string & path)
{
  std::ifstream input(path);
  if (!input.is_open()) {
    throw std::runtime_error("failed to open label file: " + path);
  }

  std::vector<std::string> labels;
  std::string line;
  while (std::getline(input, line)) {
    if (!line.empty() && line.back() == '\r') {
      line.pop_back();
    }
    if (!line.empty()) {
      labels.push_back(line);
    }
  }
  return labels;
}

Options parse_args(int argc, char ** argv)
{
  Options options;
  options.display = std::getenv("DISPLAY") != nullptr;

  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    auto require_value = [&](const std::string & name) -> std::string {
      if (i + 1 >= argc) {
        throw std::runtime_error("missing value for " + name);
      }
      return argv[++i];
    };

    if (arg == "--source") {
      options.source = require_value(arg);
    } else if (arg == "--decoder") {
      options.decoder = require_value(arg);
    } else if (arg == "--engine") {
      options.engine_path = require_value(arg);
    } else if (arg == "--labels") {
      options.label_path = require_value(arg);
    } else if (arg == "--metrics-file") {
      options.metrics_file = require_value(arg);
    } else if (arg == "--latency-samples-file") {
      options.latency_samples_file = require_value(arg);
    } else if (arg == "--ignore-thresh") {
      options.ignore_thresh = std::stof(require_value(arg));
    } else if (arg == "--gpu-id") {
      options.gpu_id = std::stoi(require_value(arg));
    } else if (arg == "--window-name") {
      options.window_name = require_value(arg);
    } else if (arg == "--max-frames") {
      options.max_frames = std::stoi(require_value(arg));
    } else if (arg == "--display") {
      options.display = true;
    } else if (arg == "--no-display") {
      options.display = false;
    } else if (arg == "--loop-file") {
      options.loop_file = true;
    } else if (arg == "--swap-rb") {
      options.swap_rb = true;
    } else if (arg == "--verbose") {
      options.verbose = true;
    } else if (arg == "--help" || arg == "-h") {
      print_usage(argv[0]);
      std::exit(0);
    } else {
      throw std::runtime_error("unknown argument: " + arg);
    }
  }

  options.engine_path = expand_user(options.engine_path);
  options.label_path = expand_user(options.label_path);
  options.metrics_file = expand_user(options.metrics_file);
  options.latency_samples_file = expand_user(options.latency_samples_file);
  return options;
}

std::pair<std::string, int> parse_udp_endpoint(const std::string & source)
{
  const std::string prefix = starts_with(source, "rtp://") ? "rtp://" : "udp://";
  const auto endpoint = source.substr(prefix.size());
  const auto colon_pos = endpoint.rfind(':');
  if (colon_pos == std::string::npos) {
    throw std::runtime_error("udp source must be in host:port form: " + source);
  }
  const std::string host = endpoint.substr(0, colon_pos);
  const int port = std::stoi(endpoint.substr(colon_pos + 1));
  if (host.empty() || port <= 0) {
    throw std::runtime_error("invalid udp source: " + source);
  }
  return {host, port};
}

std::string build_rtp_pipeline(const std::string & host, int port, const std::string & decoder)
{
  const std::string caps =
    "application/x-rtp,media=video,clock-rate=90000,encoding-name=H264,payload=96";
  std::ostringstream pipeline;
  pipeline << "udpsrc address=" << host << " port=" << port
           << " buffer-size=4194304 caps=\"" << caps << "\" ! "
           << "rtpjitterbuffer latency=50 drop-on-latency=true ! "
           << "rtph264depay ! h264parse ! ";
  if (decoder == "nvv4l2decoder") {
    pipeline << "nvv4l2decoder enable-max-performance=1 ! "
             << "nvvidconv ! video/x-raw,format=BGRx ! videoconvert ! "
             << "video/x-raw,format=BGR";
  } else {
    pipeline << decoder << " ! videoconvert ! "
             << "video/x-raw,format=BGR";
  }
  pipeline << " ! appsink drop=true max-buffers=1 sync=false";
  return pipeline.str();
}

cv::VideoCapture open_capture(const Options & options)
{
  cv::VideoCapture capture;
  if (starts_with(options.source, "udp://") || starts_with(options.source, "rtp://")) {
    const auto [host, port] = parse_udp_endpoint(options.source);
    const auto pipeline = build_rtp_pipeline(host, port, options.decoder);
    log_message("opening RTP pipeline=" + pipeline);
    capture.open(pipeline, cv::CAP_GSTREAMER);
  } else if (is_number(options.source)) {
    capture.open(std::stoi(options.source));
  } else {
    capture.open(options.source);
  }

  if (!capture.isOpened()) {
    throw std::runtime_error("failed to open source: " + options.source);
  }
  return capture;
}

std::string json_escape(const std::string & value)
{
  std::ostringstream escaped;
  for (const char ch : value) {
    switch (ch) {
      case '\\':
        escaped << "\\\\";
        break;
      case '"':
        escaped << "\\\"";
        break;
      case '\n':
        escaped << "\\n";
        break;
      case '\r':
        escaped << "\\r";
        break;
      case '\t':
        escaped << "\\t";
        break;
      default:
        escaped << ch;
        break;
    }
  }
  return escaped.str();
}

void write_metrics(const std::string & path, const Metrics & metrics)
{
  if (path.empty()) {
    return;
  }

  const std::filesystem::path file_path(path);
  const auto parent = file_path.parent_path();
  if (!parent.empty()) {
    std::filesystem::create_directories(parent);
  }

  std::ostringstream json;
  json << std::fixed << std::setprecision(3);
  json << "{\n"
       << "  \"source\": \"" << json_escape(metrics.source) << "\",\n"
       << "  \"engine_path\": \"" << json_escape(metrics.engine_path) << "\",\n"
       << "  \"timestamp_utc\": \"" << json_escape(metrics.timestamp_utc) << "\",\n"
       << "  \"processed_frames\": " << metrics.processed_frames << ",\n"
       << "  \"detection_count\": " << metrics.detection_count << ",\n"
       << "  \"last_detection_count\": " << metrics.last_detection_count << ",\n"
       << "  \"avg_latency_ms\": " << metrics.avg_latency_ms << ",\n"
       << "  \"latency_max_ms\": " << metrics.latency_max_ms << ",\n"
       << "  \"output_fps\": " << metrics.output_fps << ",\n"
       << "  \"frame_width\": " << metrics.frame_width << ",\n"
       << "  \"frame_height\": " << metrics.frame_height << ",\n"
       << "  \"model_channels\": " << metrics.model_channels << ",\n"
       << "  \"model_height\": " << metrics.model_height << ",\n"
       << "  \"model_width\": " << metrics.model_width << ",\n"
       << "  \"max_detections\": " << metrics.max_detections << ",\n"
       << "  \"display_enabled\": " << (metrics.display_enabled ? "true" : "false") << ",\n"
       << "  \"swap_rb\": " << (metrics.swap_rb ? "true" : "false") << ",\n"
       << "  \"decoder\": \"" << json_escape(metrics.decoder) << "\",\n"
       << "  \"started_at_utc\": \"" << json_escape(metrics.started_at_utc) << "\",\n"
       << "  \"ended_at_utc\": \"" << json_escape(metrics.ended_at_utc) << "\"";
  if (metrics.latency_distribution_ready) {
    json << ",\n"
         << "  \"latency_p50_ms\": " << metrics.latency_p50_ms << ",\n"
         << "  \"latency_p95_ms\": " << metrics.latency_p95_ms << ",\n"
         << "  \"latency_p99_ms\": " << metrics.latency_p99_ms;
  }
  json << "\n"
       << "}\n";

  const auto tmp_path = file_path.string() + ".tmp";
  {
    std::ofstream output(tmp_path, std::ios::trunc);
    if (!output.is_open()) {
      throw std::runtime_error("failed to open metrics temp file: " + tmp_path);
    }
    output << json.str();
  }
  std::filesystem::rename(tmp_path, file_path);
}

void write_latency_samples(
  const std::string & path,
  const std::vector<double> & latency_samples_ms)
{
  if (path.empty()) {
    return;
  }

  const std::filesystem::path file_path(path);
  const auto parent = file_path.parent_path();
  if (!parent.empty()) {
    std::filesystem::create_directories(parent);
  }

  const auto tmp_path = file_path.string() + ".tmp";
  {
    std::ofstream output(tmp_path, std::ios::trunc);
    if (!output.is_open()) {
      throw std::runtime_error("failed to open latency samples temp file: " + tmp_path);
    }
    output << "latency_ms\n";
    output << std::fixed << std::setprecision(6);
    for (const double sample : latency_samples_ms) {
      output << sample << '\n';
    }
  }
  std::filesystem::rename(tmp_path, file_path);
}

std::string class_name_for_id(const std::vector<std::string> & labels, int class_id)
{
  if (class_id >= 0 && static_cast<std::size_t>(class_id) < labels.size()) {
    return labels[static_cast<std::size_t>(class_id)];
  }
  return "class_" + std::to_string(class_id);
}

int clip_int(int value, int min_value, int max_value)
{
  return std::max(min_value, std::min(value, max_value));
}

void draw_overlay(cv::Mat & image, const Metrics & metrics)
{
  std::vector<std::string> lines;
  std::ostringstream fps;
  fps << std::fixed << std::setprecision(1) << "FPS " << metrics.output_fps;
  lines.push_back(fps.str());

  std::ostringstream latency;
  latency << std::fixed << std::setprecision(1) << "Latency " << metrics.avg_latency_ms << " ms";
  lines.push_back(latency.str());

  lines.push_back("Frames " + std::to_string(metrics.processed_frames));
  lines.push_back("Detections " + std::to_string(metrics.detection_count));

  const int origin_x = 16;
  int origin_y = 28;
  for (const auto & line : lines) {
    cv::putText(
      image, line, cv::Point(origin_x, origin_y), cv::FONT_HERSHEY_SIMPLEX, 0.7,
      cv::Scalar(0, 0, 0), 3, cv::LINE_AA);
    cv::putText(
      image, line, cv::Point(origin_x, origin_y), cv::FONT_HERSHEY_SIMPLEX, 0.7,
      cv::Scalar(0, 255, 0), 1, cv::LINE_AA);
    origin_y += 28;
  }
}

double compute_percentile(
  const std::vector<double> & ordered_samples,
  double percentile)
{
  if (ordered_samples.empty()) {
    return 0.0;
  }
  const auto index = static_cast<std::size_t>(
    std::clamp(
      std::ceil((percentile / 100.0) * static_cast<double>(ordered_samples.size())) - 1.0,
      0.0,
      static_cast<double>(ordered_samples.size() - 1U)));
  return ordered_samples[index];
}

void refresh_latency_distribution(
  Metrics & metrics,
  const std::vector<double> & latency_samples_ms)
{
  if (latency_samples_ms.empty()) {
    metrics.latency_distribution_ready = false;
    return;
  }

  auto ordered_samples = latency_samples_ms;
  std::sort(ordered_samples.begin(), ordered_samples.end());
  metrics.latency_distribution_ready = true;
  metrics.latency_p50_ms = compute_percentile(ordered_samples, 50.0);
  metrics.latency_p95_ms = compute_percentile(ordered_samples, 95.0);
  metrics.latency_p99_ms = compute_percentile(ordered_samples, 99.0);
}

}  // namespace

int main(int argc, char ** argv)
{
  try {
    std::signal(SIGINT, request_shutdown);
    std::signal(SIGTERM, request_shutdown);

    Options options = parse_args(argc, argv);
    if (!yolo::set_cuda_device(options.gpu_id)) {
      throw std::runtime_error("failed to select CUDA device " + std::to_string(options.gpu_id));
    }

    const auto labels = load_labels(options.label_path);
    // The deployed libyolo.so crashes inside yolo::Net::~Net() on this Jetson image.
    // Keep the engine alive until process exit and let the OS reclaim it.
    auto * net = new yolo::Net(options.engine_path, options.verbose);
    const auto input_dims = net->getInputDims();
    if (input_dims.size() != 3) {
      throw std::runtime_error("unexpected engine input dimensions");
    }

    Metrics metrics;
    metrics.source = options.source;
    metrics.decoder = options.decoder;
    metrics.engine_path = options.engine_path;
    metrics.model_channels = input_dims[0];
    metrics.model_height = input_dims[1];
    metrics.model_width = input_dims[2];
    metrics.max_detections = net->getMaxDetections();
    metrics.display_enabled = options.display;
    metrics.swap_rb = options.swap_rb;
    metrics.started_at_utc = now_utc_iso8601();

    log_message(
      "engine ready input_chw=" + std::to_string(metrics.model_channels) + "x" +
      std::to_string(metrics.model_height) + "x" + std::to_string(metrics.model_width) +
      " max_detections=" + std::to_string(metrics.max_detections));

    cv::VideoCapture capture = open_capture(options);
    if (options.display) {
      cv::namedWindow(options.window_name, cv::WINDOW_NORMAL);
      cv::resizeWindow(options.window_name, 1280, 720);
    }

    std::vector<float> scores(static_cast<std::size_t>(metrics.max_detections), 0.0F);
    std::vector<float> boxes(static_cast<std::size_t>(metrics.max_detections) * 4U, 0.0F);
    std::vector<float> classes(static_cast<std::size_t>(metrics.max_detections), 0.0F);

    const auto started_at = Clock::now();
    auto last_fps_at = started_at;
    auto last_metrics_write_at = started_at;
    std::uint64_t frames_since_fps = 0;
    double latency_total_ms = 0.0;
    std::vector<double> latency_samples_ms;

    for (;;) {
      if (g_shutdown_requested.load()) {
        log_message("received shutdown signal, finalizing");
        break;
      }

      cv::Mat frame;
      if (!capture.read(frame) || frame.empty()) {
        if (options.loop_file && !starts_with(options.source, "udp://") &&
            !starts_with(options.source, "rtp://")) {
          capture.release();
          capture = open_capture(options);
          continue;
        }
        log_message("input exhausted or unavailable, stopping");
        break;
      }

      metrics.frame_width = frame.cols;
      metrics.frame_height = frame.rows;

      if (options.swap_rb) {
        cv::cvtColor(frame, frame, cv::COLOR_BGR2RGB);
      }

      const auto infer_started_at = Clock::now();
      if (!net->detect(frame, scores.data(), boxes.data(), classes.data())) {
        log_message("inference failed for current frame");
        continue;
      }
      const auto infer_finished_at = Clock::now();
      const auto latency_ms = std::chrono::duration<double, std::milli>(
                                infer_finished_at - infer_started_at)
                                .count();

      metrics.processed_frames += 1;
      frames_since_fps += 1;
      latency_total_ms += latency_ms;
      metrics.avg_latency_ms = latency_total_ms / static_cast<double>(metrics.processed_frames);
      metrics.latency_max_ms = std::max(metrics.latency_max_ms, latency_ms);
      latency_samples_ms.push_back(latency_ms);

      std::uint64_t detections_this_frame = 0;
      for (int i = 0; i < metrics.max_detections; ++i) {
        if (scores[static_cast<std::size_t>(i)] < options.ignore_thresh) {
          break;
        }

        const int left = clip_int(
          static_cast<int>(boxes[static_cast<std::size_t>(4 * i)] * frame.cols), 0,
          std::max(frame.cols - 1, 0));
        const int top = clip_int(
          static_cast<int>(boxes[static_cast<std::size_t>(4 * i + 1)] * frame.rows), 0,
          std::max(frame.rows - 1, 0));
        const int width = clip_int(
          static_cast<int>(boxes[static_cast<std::size_t>(4 * i + 2)] * frame.cols), 0,
          frame.cols);
        const int height = clip_int(
          static_cast<int>(boxes[static_cast<std::size_t>(4 * i + 3)] * frame.rows), 0,
          frame.rows);
        const int right = clip_int(left + width, 0, frame.cols);
        const int bottom = clip_int(top + height, 0, frame.rows);

        const int class_id = static_cast<int>(classes[static_cast<std::size_t>(i)]);
        const auto class_name = class_name_for_id(labels, class_id);
        const float score = scores[static_cast<std::size_t>(i)];

        cv::rectangle(
          frame, cv::Point(left, top), cv::Point(right, bottom), cv::Scalar(0, 0, 255), 2,
          cv::LINE_AA);

        std::ostringstream text;
        text << class_name << ' ' << std::fixed << std::setprecision(2) << score;
        const auto caption = text.str();
        cv::putText(
          frame, caption, cv::Point(left, std::max(top - 8, 20)), cv::FONT_HERSHEY_SIMPLEX, 0.6,
          cv::Scalar(0, 0, 0), 3, cv::LINE_AA);
        cv::putText(
          frame, caption, cv::Point(left, std::max(top - 8, 20)), cv::FONT_HERSHEY_SIMPLEX, 0.6,
          cv::Scalar(0, 255, 255), 1, cv::LINE_AA);

        detections_this_frame += 1;
      }

      metrics.last_detection_count = detections_this_frame;
      metrics.detection_count += detections_this_frame;

      const auto now = Clock::now();
      const auto fps_elapsed = std::chrono::duration<double>(now - last_fps_at).count();
      if (fps_elapsed >= 1.0) {
        metrics.output_fps = static_cast<double>(frames_since_fps) / fps_elapsed;
        frames_since_fps = 0;
        last_fps_at = now;

        std::ostringstream status;
        status << std::fixed << std::setprecision(2)
               << "running fps=" << metrics.output_fps
               << " avg_latency_ms=" << metrics.avg_latency_ms
               << " processed_frames=" << metrics.processed_frames
               << " detection_count=" << metrics.detection_count;
        log_message(status.str());
      }

      metrics.timestamp_utc = now_utc_iso8601();
      draw_overlay(frame, metrics);

      if (options.display) {
        cv::imshow(options.window_name, frame);
        const int key = cv::waitKey(1);
        if (key == 27 || key == 'q' || key == 'Q') {
          log_message("received local quit key");
          break;
        }
      }

      if (!options.metrics_file.empty()) {
        const auto metrics_elapsed =
          std::chrono::duration<double>(now - last_metrics_write_at).count();
        if (metrics_elapsed >= 0.5 || metrics.processed_frames == 1) {
          write_metrics(options.metrics_file, metrics);
          last_metrics_write_at = now;
        }
      }

      if (options.max_frames > 0 &&
          metrics.processed_frames >= static_cast<std::uint64_t>(options.max_frames)) {
        log_message("reached max_frames limit");
        break;
      }

      if (g_shutdown_requested.load()) {
        log_message("shutdown requested after frame processing");
        break;
      }
    }

    metrics.ended_at_utc = now_utc_iso8601();
    metrics.timestamp_utc = now_utc_iso8601();
    refresh_latency_distribution(metrics, latency_samples_ms);
    write_metrics(options.metrics_file, metrics);
    write_latency_samples(options.latency_samples_file, latency_samples_ms);

    std::ostringstream final_status;
    final_status << std::fixed << std::setprecision(2)
                 << "completed processed_frames=" << metrics.processed_frames
                 << " detection_count=" << metrics.detection_count
                 << " avg_latency_ms=" << metrics.avg_latency_ms
                 << " output_fps=" << metrics.output_fps;
    log_message(final_status.str());
    return 0;
  } catch (const std::exception & error) {
    std::cerr << now_utc_iso8601() << " duckpark-cpp-detector error " << error.what()
              << std::endl;
    return 1;
  }
}

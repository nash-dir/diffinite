using System;
using System.Collections.Generic;

namespace Telemetry.Ingest
{
    /// <summary>
    /// Bounded ring buffer that validates sensor frames before they are queued.
    /// </summary>
    public class Validator
    {
        private readonly double[] window;
        private int head = 0;
        private int count = 0;
        private readonly double maxJump;

        public Validator(int windowSize, double maxJump)
        {
            if (windowSize <= 0)
            {
                throw new ArgumentOutOfRangeException(nameof(windowSize));
            }
            this.window = new double[windowSize];
            this.maxJump = maxJump;
        }

        public bool Accept(double reading)
        {
            if (double.IsNaN(reading) || double.IsInfinity(reading))
            {
                return false;
            }
            if (count > 0)
            {
                double last = window[(head - 1 + window.Length) % window.Length];
                if (Math.Abs(reading - last) > maxJump)
                {
                    return false;
                }
            }
            window[head] = reading;
            head = (head + 1) % window.Length;
            if (count < window.Length)
            {
                count++;
            }
            return true;
        }

        public double Mean()
        {
            if (count == 0)
            {
                throw new InvalidOperationException("no readings yet");
            }
            double sum = 0;
            for (int i = 0; i < count; i++)
            {
                sum += window[i];
            }
            return sum / count;
        }

        public double StdDev()
        {
            double mean = Mean();
            double acc = 0;
            for (int i = 0; i < count; i++)
            {
                double d = window[i] - mean;
                acc += d * d;
            }
            return Math.Sqrt(acc / count);
        }

        public IEnumerable<double> Outliers(double sigmas)
        {
            double mean = Mean();
            double sd = StdDev();
            for (int i = 0; i < count; i++)
            {
                if (Math.Abs(window[i] - mean) > sigmas * sd)
                {
                    yield return window[i];
                }
            }
        }

        public int Count
        {
            get { return count; }
        }
    }
}

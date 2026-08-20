using Microsoft.ML.OnnxRuntime;
using Microsoft.ML.OnnxRuntime.Tensors;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;

public class ComplicationPredictor
{
    private readonly InferenceSession _session;

    public ComplicationPredictor(string modelPath)
    {
        _session = new InferenceSession(modelPath);
    }

    public (float prediction, float probability) Predict(float[] features)
    {
        // Must match Python input name: "input"
        var inputTensor = new DenseTensor<float>(features, new[] { 1, features.Length });
        var inputs = new List<NamedOnnxValue>
    {
        NamedOnnxValue.CreateFromTensor("input", inputTensor)
    };

        using var results = _session.Run(inputs);

        // Log available outputs for debugging
        Debug.WriteLine("Model outputs:");
        foreach (var meta in _session.OutputMetadata)
        {
            Debug.WriteLine($" - {meta.Key}");
        }

        // Extract probabilities (since zipmap=False, this is [P(0), P(1)])
        var probOutput = results.FirstOrDefault(r => r.Name == "probabilities");
        if (probOutput == null)
            throw new InvalidOperationException("ONNX output 'probabilities' not found.");

        var probabilities = probOutput.AsEnumerable<float>().ToArray();

        // Extract predicted class (0 or 1)
        var labelOutput = results.FirstOrDefault(r => r.Name == "label");
        float prediction = labelOutput != null
            ? labelOutput.AsEnumerable<long>().First()
            : (probabilities.Length > 1 && probabilities[1] >= 0.5f ? 1f : 0f);

        float probability = probabilities.Length > 1 ? probabilities[1] : probabilities[0];

        return (prediction, probability);
    }
}
